//! Integration probe only; never included in the installed application.
#[path = "../src/clipboard.rs"]
mod clipboard;
use gtk::{glib, prelude::*};
use std::{path::PathBuf, time::Duration};

fn main() {
    gtk::init().unwrap();
    let args: Vec<_> = std::env::args().collect();
    let png = std::fs::read(&args[1]).unwrap();
    let ready = PathBuf::from(&args[2]);
    let window = gtk::Window::new(gtk::WindowType::Toplevel);
    window.set_title("Linger clipboard test");
    window.set_default_size(320, 240);
    // A hidden/no-focus caller must fail instead of reporting a false success.
    assert!(clipboard::copy_png(&window, png.clone()).is_err());
    window.show_all();
    glib::timeout_add_local(Duration::from_millis(100), move || {
        if !window.is_active() {
            return glib::ControlFlow::Continue;
        }
        clipboard::copy_png(&window, png.clone()).unwrap();
        window.close();
        std::fs::write(&ready, b"copied and closed").unwrap();
        glib::ControlFlow::Break
    });
    gtk::main();
}
