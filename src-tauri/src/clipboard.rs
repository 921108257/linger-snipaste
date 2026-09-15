use gtk::{gdk, prelude::*, TargetEntry, TargetFlags};

pub fn copy_png(window: &impl IsA<gtk::Window>, png: Vec<u8>) -> Result<(), String> {
    let window = window.as_ref();
    // Wayland requires the display connection that received keyboard focus.
    // A windowless Python worker has no valid input serial for set_selection.
    if !window.is_active() {
        return Err("复制失败：截图窗口未获得焦点，请点击截图窗口后重试。".into());
    }
    let clipboard = window.clipboard(&gdk::SELECTION_CLIPBOARD);
    let targets = [TargetEntry::new("image/png", TargetFlags::empty(), 0)];
    if !clipboard.set_with_data(&targets, move |_, selection, _| {
        selection.set(&gdk::Atom::intern("image/png"), 8, &png);
    }) {
        return Err("无法写入系统剪贴板，请重试或保存图片。".into());
    }
    // GTK owns the PNG callback for the lifetime of the clipboard selection,
    // independent of the overlay window. Flush before that window can close.
    // gtk-rs 0.18 does not wrap set_can_store. NULL/0 means all offered targets.
    use gtk::glib::translate::ToGlibPtr;
    unsafe {
        gtk::ffi::gtk_clipboard_set_can_store(clipboard.to_glib_none().0, std::ptr::null(), 0);
    }
    gtk::prelude::WidgetExt::display(window).sync();
    clipboard.store();
    Ok(())
}
