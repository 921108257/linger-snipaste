#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use serde_json::{json, Value};
use std::{
    io::{BufRead, BufReader, Write},
    path::PathBuf,
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        Mutex,
    },
};
use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Emitter, Manager, WebviewUrl, WebviewWindowBuilder,
};

struct Worker {
    child: Child,
    input: ChildStdin,
    output: BufReader<ChildStdout>,
}
impl Drop for Worker {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
struct Service {
    worker: Mutex<Option<Worker>>,
    script: PathBuf,
}
impl Service {
    fn call(&self, method: &str, params: Value) -> Result<Value, String> {
        let mut guard = self.worker.lock().map_err(|e| e.to_string())?;
        if guard
            .as_mut()
            .map(|w| w.child.try_wait().ok().flatten().is_some())
            .unwrap_or(false)
        {
            *guard = None;
        }
        if guard.is_none() {
            let executable = std::env::current_exe().map_err(|e| e.to_string())?;
            let vendor = self
                .script
                .parent()
                .and_then(|p| p.parent())
                .unwrap()
                .join("vendor");
            let mut python_paths = vec![
                vendor,
                PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../dist-deb/runtime"),
            ];
            if let Some(existing) = std::env::var_os("PYTHONPATH") {
                python_paths.extend(std::env::split_paths(&existing));
            }
            let launcher =
                if executable == std::path::Path::new("/usr/lib/linger-snipaste/linger-snipaste") {
                    PathBuf::from("/usr/bin/linger-snipaste")
                } else {
                    executable
                };
            let mut child = Command::new("/usr/bin/python3")
                .arg(&self.script)
                .env(
                    "PYTHONPATH",
                    std::env::join_paths(python_paths).map_err(|e| e.to_string())?,
                )
                .env("LINGER_LAUNCHER", launcher)
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::inherit())
                .spawn()
                .map_err(|e| format!("无法启动截图组件：{e}"))?;
            let input = child.stdin.take().ok_or("无法打开截图组件输入")?;
            let output = BufReader::new(child.stdout.take().ok_or("无法打开截图组件输出")?);
            *guard = Some(Worker {
                child,
                input,
                output,
            });
        }
        let worker = guard.as_mut().unwrap();
        let result: Result<Value, String> = (|| {
            writeln!(worker.input, "{}", json!({"method":method,"params":params}))
                .map_err(|e| e.to_string())?;
            worker.input.flush().map_err(|e| e.to_string())?;
            let mut response = String::new();
            if worker
                .output
                .read_line(&mut response)
                .map_err(|e| e.to_string())?
                == 0
            {
                return Err("截图组件已退出，请重试。".into());
            }
            let value: Value = serde_json::from_str(&response).map_err(|e| e.to_string())?;
            Ok(value)
        })();
        if result.is_err() {
            *guard = None;
        }
        let result: Value = result?;
        if let Some(error) = result.get("error") {
            if error["code"] == "CANCELLED" {
                return Err("CANCELLED".into());
            }
            return Err(error["message"].as_str().unwrap_or("操作失败").to_string());
        }
        Ok(result["result"].clone())
    }
}
struct Capturing(AtomicBool);
struct SettingsWarning(Mutex<Option<String>>);
struct RecordingShortcut(AtomicBool);
#[tauri::command]
fn record_shortcut(app: tauri::AppHandle, active: bool) {
    app.state::<RecordingShortcut>()
        .0
        .store(active, Ordering::SeqCst);
}
async fn call(app: tauri::AppHandle, method: String, params: Value) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || app.state::<Service>().call(&method, params))
        .await
        .map_err(|e| e.to_string())?
}
#[tauri::command]
async fn rpc(app: tauri::AppHandle, method: String, params: Value) -> Result<Value, String> {
    if ![
        "status",
        "metadata",
        "image",
        "import",
        "clipboard",
        "import_clipboard",
        "settings_get",
        "settings_save",
        "detect_regions",
    ]
    .contains(&method.as_str())
    {
        return Err("不支持的操作".into());
    }
    let warning = if method == "settings_get" {
        app.state::<SettingsWarning>()
            .0
            .lock()
            .map_err(|e| e.to_string())?
            .clone()
    } else {
        None
    };
    let saving_settings = method == "settings_save";
    let mut result = call(app.clone(), method, params).await?;
    if saving_settings {
        *app.state::<SettingsWarning>()
            .0
            .lock()
            .map_err(|e| e.to_string())? = None;
    }
    if let Some(warning) = warning {
        result["warning"] = json!(warning);
    }
    Ok(result)
}
async fn launch_capture(app: tauri::AppHandle, interactive: bool) -> Result<(), String> {
    if app.state::<Capturing>().0.swap(true, Ordering::SeqCst) {
        return Ok(());
    }
    if let Some(window) = app
        .webview_windows()
        .values()
        .find(|w| w.label().starts_with("capture-"))
    {
        let _ = window.set_focus();
        app.state::<Capturing>().0.store(false, Ordering::SeqCst);
        return Ok(());
    }
    if let Some(main) = app.get_webview_window("main") {
        let _ = main.hide();
    }
    // Allow the compositor to remove our launcher before requesting the desktop pixels.
    let worker_app = app.clone();
    let result = tauri::async_runtime::spawn_blocking(move || {
        std::thread::sleep(std::time::Duration::from_millis(100));
        worker_app
            .state::<Service>()
            .call("capture", json!({"interactive":interactive}))
    })
    .await
    .map_err(|e| e.to_string())
    .and_then(|r| r)
    .and_then(|shot| {
        let id = shot["id"].as_str().ok_or("截图编号缺失")?;
        WebviewWindowBuilder::new(
            &app,
            format!("capture-{id}"),
            WebviewUrl::App(format!("index.html?overlay={id}").into()),
        )
        .title("Linger 截图")
        .decorations(false)
        .fullscreen(true)
        .always_on_top(true)
        .skip_taskbar(true)
        .visible(false)
        .build()
        .map_err(|e| e.to_string())?;
        Ok(())
    });
    app.state::<Capturing>().0.store(false, Ordering::SeqCst);
    if let Err(ref error) = result {
        if error == "CANCELLED" {
            return Ok(());
        }
        if let Some(main) = app.get_webview_window("main") {
            let _ = main.show();
            let _ = main.set_focus();
            let _ = main.emit("capture-error", error);
        }
    }
    result
}
#[tauri::command]
async fn begin_capture(app: tauri::AppHandle, interactive: Option<bool>) -> Result<(), String> {
    launch_capture(app, interactive.unwrap_or(false)).await
}
#[tauri::command]
fn overlay_ready(window: tauri::WebviewWindow) -> Result<(), String> {
    window.show().map_err(|e| e.to_string())?;
    window.set_focus().map_err(|e| e.to_string())
}
#[tauri::command]
async fn save_image(
    app: tauri::AppHandle,
    window: tauri::WebviewWindow,
    id: String,
) -> Result<(), String> {
    let _ = window.set_always_on_top(false);
    let target = rfd::AsyncFileDialog::new()
        .set_file_name("linger-capture.png")
        .add_filter("PNG", &["png"])
        .save_file()
        .await;
    let result = if let Some(target) = target {
        call(
            app,
            "export".into(),
            json!({"id":id,"path":target.path().to_string_lossy()}),
        )
        .await
        .map(|_| ())
    } else {
        Err("已取消保存".into())
    };
    let _ = window.set_always_on_top(true);
    result
}
#[tauri::command]
fn pin_image(app: tauri::AppHandle, id: String, width: f64, height: f64) -> Result<(), String> {
    if id.len() != 32 || !id.chars().all(|c| c.is_ascii_hexdigit()) {
        return Err("无效的截图编号".into());
    }
    let label = format!("pin-{id}");
    if let Some(window) = app.get_webview_window(&label) {
        window.show().map_err(|e| e.to_string())?;
        return Ok(());
    }
    WebviewWindowBuilder::new(
        &app,
        label,
        WebviewUrl::App(format!("index.html?pin={id}").into()),
    )
    .title("Linger 贴图")
    .inner_size(width.clamp(280., 900.), (height + 60.).clamp(180., 800.))
    .min_inner_size(240., 160.)
    .always_on_top(true)
    .build()
    .map_err(|e| e.to_string())?;
    Ok(())
}
async fn launch_pin(app: tauri::AppHandle) {
    if let Some(window) = app
        .webview_windows()
        .values()
        .find(|w| w.label().starts_with("capture-"))
    {
        let _ = window.emit("pin-selection", ());
        return;
    }
    let result = call(app.clone(), "import_clipboard".into(), json!({}))
        .await
        .and_then(|shot| {
            pin_image(
                app.clone(),
                shot["id"].as_str().ok_or("图片编号缺失")?.into(),
                shot["width"].as_f64().unwrap_or(640.),
                shot["height"].as_f64().unwrap_or(480.),
            )
        });
    if let Err(error) = result {
        if let Some(window) = app.get_webview_window("main") {
            let _ = window.show();
            let _ = window.set_focus();
            let _ = window.emit("capture-error", error);
        }
    }
}
fn main() {
    tauri::Builder::default()
        .manage(Capturing(AtomicBool::new(false)))
        .manage(RecordingShortcut(AtomicBool::new(false)))
        .plugin(tauri_plugin_single_instance::init(|app, args, _| {
            if app.state::<RecordingShortcut>().0.load(Ordering::SeqCst)
                && args.iter().any(|a| a == "--capture" || a == "--pin")
            {
                let field = if args.iter().any(|a| a == "--capture") {
                    "captureShortcut"
                } else {
                    "pinShortcut"
                };
                let app = app.clone();
                tauri::async_runtime::spawn(async move {
                    if let Ok(settings) = call(app.clone(), "settings_get".into(), json!({})).await
                    {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.emit("shortcut-recorded", &settings[field]);
                        }
                    }
                });
                return;
            }
            if args.iter().any(|arg| arg == "--capture") {
                let app = app.clone();
                tauri::async_runtime::spawn(async move {
                    let _ = launch_capture(app, false).await;
                });
            } else if args.iter().any(|arg| arg == "--pin") {
                let app = app.clone();
                tauri::async_runtime::spawn(launch_pin(app));
            } else if args.iter().any(|arg| arg == "--background") {
            } else if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .setup(|app| {
            let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../service/daemon.py");
            let beside = std::env::current_exe()
                .ok()
                .and_then(|exe| exe.parent().map(|dir| dir.join("service/daemon.py")));
            let script = beside
                .filter(|path| path.exists())
                .or_else(|| dev.exists().then_some(dev))
                .or_else(|| {
                    app.path()
                        .resource_dir()
                        .ok()
                        .map(|dir| dir.join("_up_/service/daemon.py"))
                })
                .ok_or("找不到截图组件脚本")?;
            let service = Service {
                worker: Mutex::new(None),
                script,
            };
            let warning = service.call("settings_init", json!({})).err();
            app.manage(service);
            app.manage(SettingsWarning(Mutex::new(warning)));
            let capture = MenuItem::with_id(app, "capture", "截图", true, None::<&str>)?;
            let pin = MenuItem::with_id(app, "pin", "贴图", true, None::<&str>)?;
            let show = MenuItem::with_id(app, "show", "设置…", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&capture, &pin, &show, &quit])?;
            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("Linger 截图")
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "capture" => {
                        let app = app.clone();
                        tauri::async_runtime::spawn(async move {
                            let _ = launch_capture(app, false).await;
                        });
                    }
                    "pin" => {
                        tauri::async_runtime::spawn(launch_pin(app.clone()));
                    }
                    "show" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.set_focus();
                        }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;
            if std::env::args().any(|arg| arg == "--capture") {
                let handle = app.handle().clone();
                tauri::async_runtime::spawn(async move {
                    let _ = launch_capture(handle, false).await;
                });
            } else if std::env::args().any(|arg| arg == "--pin") {
                tauri::async_runtime::spawn(launch_pin(app.handle().clone()));
            } else if !std::env::args().any(|arg| arg == "--background") {
                if let Some(window) = app.get_webview_window("main") {
                    window.show()?;
                }
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() == "main" {
                if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let _ = window.hide();
                }
                if matches!(
                    event,
                    tauri::WindowEvent::Focused(false) | tauri::WindowEvent::CloseRequested { .. }
                ) {
                    window
                        .app_handle()
                        .state::<RecordingShortcut>()
                        .0
                        .store(false, Ordering::SeqCst);
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            rpc,
            pin_image,
            save_image,
            begin_capture,
            overlay_ready,
            record_shortcut
        ])
        .build(tauri::generate_context!())
        .expect("Failed to start Linger")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                if let Ok(mut worker) = app.state::<Service>().worker.lock() {
                    worker.take();
                }
            }
        });
}
