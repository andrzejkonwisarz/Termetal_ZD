import os
import json
import ftplib
import threading
from datetime import datetime
from PIL import Image as PILImage

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.camera import Camera
from kivy.uix.popup import Popup
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.utils import platform

if platform == 'android':
    from android.permissions import request_permissions, Permission
    request_permissions([
        Permission.CAMERA,
        Permission.INTERNET,
        Permission.WRITE_EXTERNAL_STORAGE,
        Permission.READ_EXTERNAL_STORAGE
    ])

CONFIG_FILE = "termetal_config.json"

DEFAULT_CONFIG = {
    "ftp_host": "192.168.1.100",
    "ftp_port": 21,
    "ftp_user": "user",
    "ftp_pass": "password",
    "ftp_base_dir": "/zdjecia",
    "scale_percent": 50,
    "jpeg_quality": 80,
    "pin": "1234",
    "font_size": 18,
    "theme": "Ciemny"
}

THEMES = {
    "Ciemny": {"bg": (0.12, 0.12, 0.14, 1), "btn": (0.25, 0.45, 0.75, 1), "text": (1, 1, 1, 1)},
    "Jasny": {"bg": (0.94, 0.94, 0.96, 1), "btn": (0.2, 0.5, 0.8, 1), "text": (0.1, 0.1, 0.1, 1)},
    "Przemysłowy (Termetal)": {"bg": (0.15, 0.18, 0.22, 1), "btn": (0.85, 0.45, 0.1, 1), "text": (0.95, 0.95, 0.95, 1)}
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in DEFAULT_CONFIG.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)


class MainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_subfolder = ""
        self.photo_counter = 0

        self.root_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
        
        top_bar = BoxLayout(orientation="horizontal", size_hint_y=0.1, spacing=10)
        self.title_label = Label(text="Termetal_ZD", bold=True, halign="left")
        self.settings_btn = Button(text="Ustawienia", size_hint_x=0.35)
        self.settings_btn.bind(on_release=self.ask_pin)
        top_bar.add_widget(self.title_label)
        top_bar.add_widget(self.settings_btn)
        self.root_layout.add_widget(top_bar)

        try:
            self.camera = Camera(play=True, resolution=(1280, 720), size_hint_y=0.65)
            self.root_layout.add_widget(self.camera)
        except Exception as e:
            self.camera = None
            self.root_layout.add_widget(Label(text=f"Błąd inicjalizacji kamery: {e}", size_hint_y=0.65))

        self.status_label = Label(text="Folder: Brak (kliknij 'Nowa grupa')", size_hint_y=0.08)
        self.root_layout.add_widget(self.status_label)

        bottom_bar = BoxLayout(orientation="horizontal", size_hint_y=0.17, spacing=10)
        self.new_group_btn = Button(text="Nowa grupa\n(Podfolder)")
        self.new_group_btn.bind(on_release=self.show_folder_popup)

        self.capture_btn = Button(text="ZRÓB ZDJĘCIE\nI WYŚLIJ FTP", bold=True)
        self.capture_btn.bind(on_release=self.take_photo)

        bottom_bar.add_widget(self.new_group_btn)
        bottom_bar.add_widget(self.capture_btn)
        self.root_layout.add_widget(bottom_bar)

        self.add_widget(self.root_layout)

    def on_pre_enter(self):
        self.apply_styles()
        if not self.current_subfolder:
            Clock.schedule_once(lambda dt: self.show_folder_popup(None), 0.3)

    def apply_styles(self):
        cfg = App.get_running_app().config_data
        theme = THEMES.get(cfg["theme"], THEMES["Ciemny"])
        font_sz = cfg["font_size"]

        Window.clearcolor = theme["bg"]
        self.title_label.font_size = font_sz + 4
        self.title_label.color = theme["text"]
        self.status_label.font_size = font_sz - 2
        self.status_label.color = theme["text"]

        for btn in [self.settings_btn, self.new_group_btn, self.capture_btn]:
            btn.font_size = font_sz
            btn.background_normal = ""
            btn.background_color = theme["btn"]
            btn.color = (1, 1, 1, 1)

    def show_folder_popup(self, instance):
        content = BoxLayout(orientation="vertical", spacing=10, padding=10)
        info = Label(text="Podaj nazwę podfolderu dla grupy zdjęć:")
        folder_input = TextInput(
            text=datetime.now().strftime("Zlecenie_%Y%m%d_%H%M"),
            multiline=False
        )
        btn_ok = Button(text="Zatwierdź", size_hint_y=0.4)
        content.add_widget(info)
        content.add_widget(folder_input)
        content.add_widget(btn_ok)

        popup = Popup(title="Nowa grupa zdjęć", content=content, size_hint=(0.85, 0.4), auto_dismiss=False)

        def confirm(btn):
            name = folder_input.text.strip().replace(" ", "_")
            if name:
                self.current_subfolder = name
                self.photo_counter = 0
                self.status_label.text = f"Folder: {self.current_subfolder} | Zdjęć: 0"
                popup.dismiss()

        btn_ok.bind(on_release=confirm)
        popup.open()

    def ask_pin(self, instance):
        content = BoxLayout(orientation="vertical", spacing=10, padding=10)
        pin_input = TextInput(password=True, input_filter="int", multiline=False, hint_text="Wpisz 4-cyfrowy PIN")
        error_lbl = Label(text="", color=(1, 0.3, 0.3, 1))
        btn_box = BoxLayout(spacing=10, size_hint_y=0.45)
        btn_cancel = Button(text="Anuluj")
        btn_ok = Button(text="Wejdź")

        btn_box.add_widget(btn_cancel)
        btn_box.add_widget(btn_ok)
        content.add_widget(pin_input)
        content.add_widget(error_lbl)
        content.add_widget(btn_box)

        popup = Popup(title="Zabezpieczenie PIN", content=content, size_hint=(0.8, 0.4))

        def verify(btn):
            correct_pin = App.get_running_app().config_data.get("pin", "1234")
            if pin_input.text == correct_pin:
                popup.dismiss()
                self.manager.current = "settings"
            else:
                error_lbl.text = "Błędny kod PIN!"
                pin_input.text = ""

        btn_cancel.bind(on_release=popup.dismiss)
        btn_ok.bind(on_release=verify)
        popup.open()

    def take_photo(self, instance):
        if not self.current_subfolder:
            self.show_folder_popup(None)
            return

        if not self.camera:
            self.status_label.text = "Brak dostępu do aparatu!"
            return

        self.photo_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.current_subfolder}_{self.photo_counter:03d}_{timestamp}.jpg"
        raw_path = os.path.join(App.get_running_app().user_data_dir, "temp_raw.png")
        final_path = os.path.join(App.get_running_app().user_data_dir, filename)

        self.camera.export_to_png(raw_path)
        self.status_label.text = f"Przetwarzanie i wysyłanie: {filename}..."

        threading.Thread(
            target=self.process_and_upload,
            args=(raw_path, final_path, filename, self.current_subfolder),
            daemon=True
        ).start()

    def process_and_upload(self, raw_path, final_path, filename, subfolder):
        cfg = App.get_running_app().config_data
        try:
            img = PILImage.open(raw_path).convert("RGB")
            scale = cfg["scale_percent"] / 100.0
            new_size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
            img = img.resize(new_size, PILImage.Resampling.LANCZOS)
            img.save(final_path, "JPEG", quality=int(cfg["jpeg_quality"]), optimize=True)

            ftp = ftplib.FTP()
            ftp.connect(cfg["ftp_host"], int(cfg["ftp_port"]), timeout=15)
            ftp.login(cfg["ftp_user"], cfg["ftp_pass"])

            base_dir = cfg["ftp_base_dir"].strip()
            if base_dir:
                self._ftp_cd_or_create(ftp, base_dir)
            self._ftp_cd_or_create(ftp, subfolder)

            with open(final_path, "rb") as f:
                ftp.storbinary(f"STOR {filename}", f)

            ftp.quit()

            if os.path.exists(raw_path):
                os.remove(raw_path)
            if os.path.exists(final_path):
                os.remove(final_path)

            Clock.schedule_once(
                lambda dt: setattr(
                    self.status_label, "text",
                    f"Wysłano ({self.photo_counter}): {subfolder}/{filename}"
                )
            )
        except Exception as e:
            Clock.schedule_once(
                lambda dt: setattr(self.status_label, "text", f"Błąd FTP: {str(e)}")
            )

    def _ftp_cd_or_create(self, ftp, path):
        for part in path.split("/"):
            if not part:
                continue
            try:
                ftp.cwd(part)
            except ftplib.error_perm:
                ftp.mkd(part)
                ftp.cwd(part)


class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation="vertical", padding=12, spacing=8)

        header = Label(text="USTAWIENIA TERMETAL_ZD", size_hint_y=0.08, bold=True)
        layout.add_widget(header)

        form = GridLayout(cols=2, spacing=6, size_hint_y=0.8)

        form.add_widget(Label(text="Serwer FTP (Host/IP):"))
        self.host_in = TextInput(multiline=False)
        form.add_widget(self.host_in)

        form.add_widget(Label(text="Port FTP:"))
        self.port_in = TextInput(multiline=False, input_filter="int")
        form.add_widget(self.port_in)

        form.add_widget(Label(text="Użytkownik FTP:"))
        self.user_in = TextInput(multiline=False)
        form.add_widget(self.user_in)

        form.add_widget(Label(text="Hasło FTP:"))
        self.pass_in = TextInput(multiline=False, password=True)
        form.add_widget(self.pass_in)

        form.add_widget(Label(text="Katalog bazowy FTP:"))
        self.dir_in = TextInput(multiline=False)
        form.add_widget(self.dir_in)

        self.scale_lbl = Label(text="Skala rozdzielczości: 50%")
        self.scale_slider = Slider(min=10, max=100, value=50, step=5)
        self.scale_slider.bind(value=lambda inst, val: setattr(self.scale_lbl, "text", f"Skala rozdzielczości: {int(val)}%"))
        form.add_widget(self.scale_lbl)
        form.add_widget(self.scale_slider)

        self.qual_lbl = Label(text="Jakość kompresji JPEG: 80%")
        self.qual_slider = Slider(min=20, max=100, value=80, step=5)
        self.qual_slider.bind(value=lambda inst, val: setattr(self.qual_lbl, "text", f"Jakość kompresji JPEG: {int(val)}%"))
        form.add_widget(self.qual_lbl)
        form.add_widget(self.qual_slider)

        form.add_widget(Label(text="Kod PIN (4 cyfry):"))
        self.pin_in = TextInput(multiline=False, input_filter="int", max_text_length=4)
        form.add_widget(self.pin_in)

        self.font_lbl = Label(text="Wielkość czcionki: 18")
        self.font_slider = Slider(min=12, max=30, value=18, step=1)
        self.font_slider.bind(value=lambda inst, val: setattr(self.font_lbl, "text", f"Wielkość czcionki: {int(val)}"))
        form.add_widget(self.font_lbl)
        form.add_widget(self.font_slider)

        form.add_widget(Label(text="Kolorystyka ekranu:"))
        self.theme_spinner = Spinner(text="Ciemny", values=list(THEMES.keys()))
        form.add_widget(self.theme_spinner)

        layout.add_widget(form)

        btns = BoxLayout(size_hint_y=0.12, spacing=10)
        back_btn = Button(text="Anuluj")
        back_btn.bind(on_release=self.go_back)
        save_btn = Button(text="Zapisz ustawienia", bold=True)
        save_btn.bind(on_release=self.save_and_exit)

        btns.add_widget(back_btn)
        btns.add_widget(save_btn)
        layout.add_widget(btns)

        self.add_widget(layout)

    def on_pre_enter(self):
        cfg = App.get_running_app().config_data
        self.host_in.text = str(cfg["ftp_host"])
        self.port_in.text = str(cfg["ftp_port"])
        self.user_in.text = str(cfg["ftp_user"])
        self.pass_in.text = str(cfg["ftp_pass"])
        self.dir_in.text = str(cfg["ftp_base_dir"])
        self.scale_slider.value = cfg["scale_percent"]
        self.qual_slider.value = cfg["jpeg_quality"]
        self.pin_in.text = str(cfg["pin"])
        self.font_slider.value = cfg["font_size"]
        self.theme_spinner.text = cfg["theme"]

    def save_and_exit(self, instance):
        cfg = App.get_running_app().config_data
        cfg["ftp_host"] = self.host_in.text.strip()
        cfg["ftp_port"] = int(self.port_in.text or 21)
        cfg["ftp_user"] = self.user_in.text.strip()
        cfg["ftp_pass"] = self.pass_in.text
        cfg["ftp_base_dir"] = self.dir_in.text.strip()
        cfg["scale_percent"] = int(self.scale_slider.value)
        cfg["jpeg_quality"] = int(self.qual_slider.value)
        if len(self.pin_in.text) == 4:
            cfg["pin"] = self.pin_in.text
        cfg["font_size"] = int(self.font_slider.value)
        cfg["theme"] = self.theme_spinner.text

        save_config(cfg)
        self.go_back(None)

    def go_back(self, instance):
        self.manager.current = "main"


class TermetalZDApp(App):
    def build(self):
        self.title = "Termetal_ZD"
        self.config_data = load_config()
        sm = ScreenManager()
        sm.add_widget(MainScreen(name="main"))
        sm.add_widget(SettingsScreen(name="settings"))
        return sm


if __name__ == "__main__":
    TermetalZDApp().run()
