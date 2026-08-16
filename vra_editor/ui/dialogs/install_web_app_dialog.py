import getpass
import os
import platform

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QCheckBox, QPushButton,
    QRadioButton, QButtonGroup, QLabel, QFileDialog, QMessageBox, QGroupBox,
    QStackedWidget, QWidget,
)

from ...config import DEFAULT_CONFIG_PATH
from ...core.web_installer import (
    BundleMissingError,
    InstallOptions,
    NssmMissingError,
    WindowsInstallOptions,
    generate_install_script,
    generate_windows_install_script,
)

_LINUX_TAB = 0
_WINDOWS_TAB = 1


# noinspection PyUnresolvedReferences
class InstallWebAppDialog(QDialog):
    """Generates a self-contained install script for the web companion
    app, for either Linux (systemd + Nginx/Apache/none) or Windows
    (a vendored NSSM service + IIS/none) -- see core/web_installer.py
    for what each generated script actually does. This dialog itself
    makes no system changes and needs no elevated privileges either
    way: it only writes the generated file wherever the user chooses
    to save it. The user reviews and runs that script themselves (with
    sudo on Linux, elevated on Windows).

    Usage:
        dlg = InstallWebAppDialog(parent=self)
        dlg.exec()
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Install Web Companion")
        self.setModal(True)
        self.resize(560, 560)

        self.os_group: QButtonGroup | None = None
        self.deployment_stack: QStackedWidget | None = None
        self.proxy_stack: QStackedWidget | None = None

        # Linux fields
        self.install_dir_edit: QLineEdit | None = None
        self.port_edit: QLineEdit | None = None
        self.service_user_edit: QLineEdit | None = None
        self.config_path_edit: QLineEdit | None = None
        self.proxy_group: QButtonGroup | None = None
        self.server_name_edit: QLineEdit | None = None

        # Windows fields
        self.win_install_dir_edit: QLineEdit | None = None
        self.win_port_edit: QLineEdit | None = None
        self.win_config_path_edit: QLineEdit | None = None
        self.win_site_name_edit: QLineEdit | None = None
        self.win_proxy_group: QButtonGroup | None = None
        self.win_server_name_edit: QLineEdit | None = None

        # Shared
        self.ldap_enable_check: QCheckBox | None = None
        self.ldap_server_edit: QLineEdit | None = None
        self.ldap_bind_pattern_edit: QLineEdit | None = None
        self.ldap_use_ssl_check: QCheckBox | None = None
        self.local_auth_check: QCheckBox | None = None
        self.local_auth_warning_label: QLabel | None = None

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)

        intro = QLabel(
            "Generates a script that deploys this web companion app as a background service, "
            "with a reverse proxy in front of it. Review the script before running it -- it "
            "makes real system changes, and needs elevated privileges. "
            "<b>TLS/certificates are not configured</b> -- set those up on your reverse proxy "
            "separately."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #444;")
        outer.addWidget(intro)

        outer.addWidget(self._build_os_group())

        self.deployment_stack = QStackedWidget()
        self.deployment_stack.addWidget(self._build_linux_deployment_group())
        self.deployment_stack.addWidget(self._build_windows_deployment_group())
        outer.addWidget(self.deployment_stack)

        self.proxy_stack = QStackedWidget()
        self.proxy_stack.addWidget(self._build_linux_proxy_group())
        self.proxy_stack.addWidget(self._build_windows_proxy_group())
        outer.addWidget(self.proxy_stack)

        outer.addWidget(self._build_auth_group())

        # Wired here, not where the individual widgets are built --
        # service_user_edit (Linux deployment group) and local_auth_check
        # (auth group) are constructed in different methods, and the
        # warning needs both to exist first.
        self.local_auth_check.toggled.connect(self._update_local_auth_warning)
        self.service_user_edit.textChanged.connect(self._update_local_auth_warning)

        # Default tab follows this machine's own OS -- a reasonable
        # starting guess (most likely to match the intended target),
        # not a constraint; every field stays fully editable either
        # way, including for the common "generate here, deploy to a
        # different machine entirely" case.
        default_tab = _WINDOWS_TAB if platform.system() == 'Windows' else _LINUX_TAB
        self.os_group.buttons()[default_tab].setChecked(True)
        self._on_os_changed(default_tab)

        generate_btn = QPushButton("Generate Install Script...")
        generate_btn.clicked.connect(self._on_generate)
        outer.addWidget(generate_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        outer.addWidget(close_btn)

    def _build_os_group(self) -> QGroupBox:
        group = QGroupBox("Target OS")
        layout = QVBoxLayout(group)

        self.os_group = QButtonGroup(self)
        linux_radio = QRadioButton("Linux (systemd + Nginx/Apache)")
        windows_radio = QRadioButton("Windows (NSSM service + IIS)")
        for index, radio in ((_LINUX_TAB, linux_radio), (_WINDOWS_TAB, windows_radio)):
            self.os_group.addButton(radio, index)
            layout.addWidget(radio)
        self.os_group.idClicked.connect(self._on_os_changed)

        return group

    def _on_os_changed(self, index: int):
        self.deployment_stack.setCurrentIndex(index)
        self.proxy_stack.setCurrentIndex(index)
        self.local_auth_check.setText(
            "Enable local Windows accounts" if index == _WINDOWS_TAB
            else "Enable local Linux system accounts (PAM)"
        )
        self._update_local_auth_warning()

    def _build_linux_deployment_group(self) -> QWidget:
        group = QGroupBox("Deployment")
        form = QFormLayout(group)

        self.install_dir_edit = QLineEdit('/opt/vra-editor-web')
        form.addRow("Install directory:", self.install_dir_edit)

        self.port_edit = QLineEdit('8000')
        self.port_edit.setToolTip(
            "Internal port the web app listens on (127.0.0.1 only) -- the reverse proxy is "
            "what's actually exposed."
        )
        form.addRow("Port:", self.port_edit)

        self.service_user_edit = QLineEdit(getpass.getuser())
        self.service_user_edit.setToolTip("The OS account the systemd service runs as.")
        form.addRow("Run service as:", self.service_user_edit)

        self.config_path_edit = QLineEdit(str(DEFAULT_CONFIG_PATH))
        self.config_path_edit.setToolTip(
            "Which vra-config.ini the web app reads -- defaults to this desktop app's own, so "
            "the web app sees the same archive locations. Change this if deploying to a "
            "different machine or account."
        )
        form.addRow("Config file:", self.config_path_edit)

        return group

    def _build_windows_deployment_group(self) -> QWidget:
        group = QGroupBox("Deployment")
        form = QFormLayout(group)

        self.win_install_dir_edit = QLineEdit(r'C:\VRA-Editor-Web')
        form.addRow("Install directory:", self.win_install_dir_edit)

        self.win_port_edit = QLineEdit('8000')
        self.win_port_edit.setToolTip(
            "Internal port the web app listens on (127.0.0.1 only) -- the reverse proxy is "
            "what's actually exposed."
        )
        form.addRow("Port:", self.win_port_edit)

        self.win_config_path_edit = QLineEdit(r'C:\ProgramData\VRA-Editor\config.ini')
        self.win_config_path_edit.setToolTip(
            "Which vra-config.ini the web app reads. Defaults to a machine-wide location, "
            "not this desktop install's own -- the Windows service runs as LocalSystem "
            "(deliberately, to avoid ever needing a service-account password), which has no "
            "meaningful per-user profile to reuse. Point this at an existing config.ini instead "
            "if you want to share archive locations with a desktop install on the same machine."
        )
        form.addRow("Config file:", self.win_config_path_edit)

        return group

    def _build_linux_proxy_group(self) -> QWidget:
        group = QGroupBox("Reverse Proxy")
        layout = QVBoxLayout(group)

        self.proxy_group = QButtonGroup(self)
        nginx_radio = QRadioButton("Nginx")
        nginx_radio.setChecked(True)
        apache_radio = QRadioButton("Apache")
        none_radio = QRadioButton("None (systemd service only)")
        for value, radio in (('nginx', nginx_radio), ('apache', apache_radio), ('none', none_radio)):
            self.proxy_group.addButton(radio)
            radio.setProperty('proxy_value', value)
            layout.addWidget(radio)

        form = QFormLayout()
        self.server_name_edit = QLineEdit()
        self.server_name_edit.setPlaceholderText("e.g. vra.yourarchive.org")
        form.addRow("Server name:", self.server_name_edit)
        layout.addLayout(form)

        return group

    def _build_windows_proxy_group(self) -> QWidget:
        group = QGroupBox("Reverse Proxy")
        layout = QVBoxLayout(group)

        self.win_proxy_group = QButtonGroup(self)
        iis_radio = QRadioButton("IIS")
        iis_radio.setChecked(True)
        none_radio = QRadioButton("None (Windows service only)")
        for value, radio in (('iis', iis_radio), ('none', none_radio)):
            self.win_proxy_group.addButton(radio)
            radio.setProperty('proxy_value', value)
            layout.addWidget(radio)

        form = QFormLayout()
        self.win_server_name_edit = QLineEdit()
        self.win_server_name_edit.setPlaceholderText("e.g. vra.yourarchive.org")
        form.addRow("Server name (host header):", self.win_server_name_edit)

        self.win_site_name_edit = QLineEdit('VRA-Editor-Web')
        self.win_site_name_edit.setToolTip(
            "The new IIS site's own name -- created alongside whatever else this server "
            "already serves (e.g. Default Web Site), never replacing it."
        )
        form.addRow("IIS site name:", self.win_site_name_edit)
        layout.addLayout(form)

        note = QLabel(
            "Needs the IIS URL Rewrite and Application Request Routing modules -- the "
            "generated script checks for these and links to Microsoft's downloads if either "
            "is missing, rather than installing them for you."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666; font-size: 0.9em;")
        layout.addWidget(note)

        return group

    def _build_auth_group(self) -> QGroupBox:
        group = QGroupBox("Authentication (for web login)")
        layout = QVBoxLayout(group)

        self.ldap_enable_check = QCheckBox("Enable LDAP directory login")
        self.ldap_enable_check.setChecked(True)  # preserves this dialog's previous, LDAP-only default
        layout.addWidget(self.ldap_enable_check)

        ldap_form = QFormLayout()
        self.ldap_server_edit = QLineEdit()
        self.ldap_server_edit.setPlaceholderText("ldap://ldap.yourarchive.org:389")
        ldap_form.addRow("Server:", self.ldap_server_edit)

        self.ldap_bind_pattern_edit = QLineEdit()
        self.ldap_bind_pattern_edit.setPlaceholderText("cn={username},ou=people,dc=example,dc=org")
        self.ldap_bind_pattern_edit.setToolTip(
            "A bind DN template -- {username} is replaced with whatever the cataloguer types at "
            "the web login form. Use '{username}@example.org' or 'EXAMPLE\\\\{username}' for "
            "Active Directory's UPN/NetBIOS forms instead."
        )
        ldap_form.addRow("Bind pattern:", self.ldap_bind_pattern_edit)

        self.ldap_use_ssl_check = QCheckBox()
        ldap_form.addRow("Use SSL/TLS to LDAP:", self.ldap_use_ssl_check)
        layout.addLayout(ldap_form)

        # Only meaningful/required while LDAP itself is enabled.
        self.ldap_enable_check.toggled.connect(self.ldap_server_edit.setEnabled)
        self.ldap_enable_check.toggled.connect(self.ldap_bind_pattern_edit.setEnabled)
        self.ldap_enable_check.toggled.connect(self.ldap_use_ssl_check.setEnabled)

        self.local_auth_check = QCheckBox("Enable local system accounts")
        self.local_auth_check.setToolTip(
            "Validates credentials against this machine's own OS accounts (PAM on Linux, local "
            "Windows accounts on Windows) as an additional login method alongside LDAP -- useful "
            "as a break-glass admin login not in the directory. Off by default: this widens what "
            "a compromised or guessed web login can be used to test."
        )
        layout.addWidget(self.local_auth_check)

        self.local_auth_warning_label = QLabel()
        self.local_auth_warning_label.setWordWrap(True)
        self.local_auth_warning_label.setStyleSheet("color: #a15c00;")
        self.local_auth_warning_label.setVisible(False)
        layout.addWidget(self.local_auth_warning_label)

        return group

    def _update_local_auth_warning(self):
        """PAM needs the service to run as root (or in the 'shadow'
        group) to read /etc/shadow -- see the generated Linux script's
        own runtime warning (web_installer.py). Windows needs no
        equivalent warning: LocalSystem always holds the privilege
        LogonUser needs."""
        is_linux = self.os_group.checkedId() == _LINUX_TAB
        service_user = self.service_user_edit.text().strip() if self.service_user_edit else ''
        show = is_linux and self.local_auth_check.isChecked() and service_user != 'root'
        if show:
            self.local_auth_warning_label.setText(
                f"Local-account login requires the service to run as root (or in the 'shadow' "
                f"group) to read /etc/shadow. \"Run service as\" is currently \"{service_user}\" -- "
                "local logins will likely fail until this is fixed. The generated script will "
                "also warn about this at runtime."
            )
        self.local_auth_warning_label.setVisible(show)

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------

    def _selected_proxy(self, group: QButtonGroup) -> str:
        checked = group.checkedButton()
        return checked.property('proxy_value') if checked else 'none'

    # Reserved for the reverse proxy's own public listener -- 443 isn't
    # actually opened by anything this dialog generates (TLS is out of
    # scope), but it's blocked too since an operator adding TLS
    # themselves later would hit the exact same conflict.
    _RESERVED_PROXY_PORTS = (80, 443)

    def _check_port_not_reserved(self, port: int, reverse_proxy: str) -> bool:
        """False (after showing an explanatory warning) if `port` --
        the INTERNAL port the app itself listens on -- collides with a
        port the reverse proxy needs for its own public listener. Real,
        previously-hit failure mode: IIS/Nginx/Apache's own HTTP
        listener exclusively reserves :80 (Windows' HTTP.SYS in
        particular blocks any other process from binding it at all,
        even scoped to 127.0.0.1 only) -- a plausible-looking value
        here silently produces a service stuck crash-looping, not an
        error at generate time, unless this is caught first."""
        if reverse_proxy != 'none' and port in self._RESERVED_PROXY_PORTS:
            QMessageBox.warning(
                self, "Port conflict",
                f"Port {port} is reserved for the reverse proxy's own public listener -- "
                "the \"Port\" field above is a different, private port the web app itself "
                "listens on (127.0.0.1 only), which the reverse proxy then forwards to. "
                "Using the same port for both won't work: the reverse proxy already owns "
                "it, so the app can't also bind it, and the service will fail to start. "
                "Leave this as 8000, or pick any other unused port.",
            )
            return False
        return True

    def _on_generate(self):
        is_windows = self.os_group.checkedId() == _WINDOWS_TAB
        if is_windows:
            self._on_generate_windows()
        else:
            self._on_generate_linux()

    def _on_generate_linux(self):
        install_dir = self.install_dir_edit.text().strip()
        config_path = self.config_path_edit.text().strip()
        service_user = self.service_user_edit.text().strip()
        server_name = self.server_name_edit.text().strip()
        ldap_enabled = self.ldap_enable_check.isChecked()
        local_auth_enabled = self.local_auth_check.isChecked()
        ldap_server = self.ldap_server_edit.text().strip() if ldap_enabled else ''
        ldap_bind_pattern = self.ldap_bind_pattern_edit.text().strip() if ldap_enabled else ''
        reverse_proxy = self._selected_proxy(self.proxy_group)

        port = self._parse_port(self.port_edit.text().strip())
        if port is None:
            return
        if not self._check_port_not_reserved(port, reverse_proxy):
            return

        missing = []
        if not install_dir:
            missing.append("Install directory")
        if not config_path:
            missing.append("Config file")
        if not service_user:
            missing.append("Run service as")
        if reverse_proxy != 'none' and not server_name:
            missing.append("Server name")
        if ldap_enabled and not ldap_server:
            missing.append("LDAP server")
        if ldap_enabled and not ldap_bind_pattern:
            missing.append("LDAP bind pattern")
        if not ldap_enabled and not local_auth_enabled:
            missing.append("At least one authentication method (LDAP or local system accounts)")
        if missing:
            QMessageBox.warning(self, "Missing fields", "Fill in: " + ", ".join(missing))
            return

        options = InstallOptions(
            install_dir=install_dir,
            port=port,
            service_user=service_user,
            config_path=config_path,
            reverse_proxy=reverse_proxy,
            server_name=server_name,
            ldap_server=ldap_server,
            ldap_bind_pattern=ldap_bind_pattern,
            ldap_use_ssl=self.ldap_use_ssl_check.isChecked(),
            local_auth_enabled=local_auth_enabled,
        )

        try:
            script = generate_install_script(options)
        except BundleMissingError as e:
            self._show_bundle_missing_error(e)
            return

        self._save_script(
            script, default_name="install-vra-web.sh", chmod_executable=True,
            run_instructions="sudo bash {dest}",
        )

    def _on_generate_windows(self):
        install_dir = self.win_install_dir_edit.text().strip()
        config_path = self.win_config_path_edit.text().strip()
        site_name = self.win_site_name_edit.text().strip()
        server_name = self.win_server_name_edit.text().strip()
        ldap_enabled = self.ldap_enable_check.isChecked()
        local_auth_enabled = self.local_auth_check.isChecked()
        ldap_server = self.ldap_server_edit.text().strip() if ldap_enabled else ''
        ldap_bind_pattern = self.ldap_bind_pattern_edit.text().strip() if ldap_enabled else ''
        reverse_proxy = self._selected_proxy(self.win_proxy_group)

        port = self._parse_port(self.win_port_edit.text().strip())
        if port is None:
            return
        if not self._check_port_not_reserved(port, reverse_proxy):
            return

        missing = []
        if not install_dir:
            missing.append("Install directory")
        if not config_path:
            missing.append("Config file")
        if reverse_proxy != 'none':
            if not server_name:
                missing.append("Server name")
            if not site_name:
                missing.append("IIS site name")
        if ldap_enabled and not ldap_server:
            missing.append("LDAP server")
        if ldap_enabled and not ldap_bind_pattern:
            missing.append("LDAP bind pattern")
        if not ldap_enabled and not local_auth_enabled:
            missing.append("At least one authentication method (LDAP or local system accounts)")
        if missing:
            QMessageBox.warning(self, "Missing fields", "Fill in: " + ", ".join(missing))
            return

        options = WindowsInstallOptions(
            install_dir=install_dir,
            port=port,
            config_path=config_path,
            reverse_proxy=reverse_proxy,
            server_name=server_name,
            site_name=site_name or 'VRA-Editor-Web',
            ldap_server=ldap_server,
            ldap_bind_pattern=ldap_bind_pattern,
            ldap_use_ssl=self.ldap_use_ssl_check.isChecked(),
            local_auth_enabled=local_auth_enabled,
        )

        try:
            script = generate_windows_install_script(options)
        except BundleMissingError as e:
            self._show_bundle_missing_error(e)
            return
        except NssmMissingError as e:
            QMessageBox.critical(
                self, "NSSM binary not found",
                f"{e}\n\nThis usually means this build wasn't packaged with the vendored NSSM "
                "binary -- rebuild via packaging/VRA_Editor.spec, with packaging/windows/nssm.exe "
                "present.",
            )
            return

        self._save_script(
            script, default_name="install-vra-web.ps1", chmod_executable=False,
            # Explorer's own "Run with PowerShell" context-menu entry does
            # neither of the two things this script actually needs -- it
            # doesn't elevate, and it doesn't bypass the default execution
            # policy -- so it fails silently (the window flashes and closes
            # before the error is readable) rather than doing anything.
            # There's no built-in "as Administrator" variant of that menu
            # item, so don't suggest it; an elevated prompt is the only
            # reliable path.
            run_instructions="Open an elevated PowerShell prompt (Start menu -> search "
                              "\"PowerShell\" -> right-click -> Run as administrator), then: "
                              "powershell -ExecutionPolicy Bypass -File {dest}",
        )

    def _parse_port(self, port_text: str) -> int | None:
        if not port_text.isdigit():
            QMessageBox.warning(self, "Invalid port", "Port must be a number.")
            return None
        return int(port_text)

    def _show_bundle_missing_error(self, error: Exception):
        QMessageBox.critical(
            self, "Web app bundle not found",
            f"{error}\n\nThis usually means this build wasn't packaged with the web companion "
            "bundle -- rebuild via packaging/VRA_Editor.spec.",
        )

    def _save_script(self, script: bytes, default_name: str, chmod_executable: bool, run_instructions: str):
        dest, _filter = QFileDialog.getSaveFileName(self, "Save install script", default_name)
        if not dest:
            return

        try:
            with open(dest, 'wb') as f:
                f.write(script)
            if chmod_executable:
                try:
                    os.chmod(dest, 0o755)
                except OSError:
                    pass  # best-effort -- harmless if this build's OS doesn't support POSIX modes
        except OSError as e:
            QMessageBox.critical(self, "Couldn't save script", str(e))
            return

        QMessageBox.information(
            self, "Script ready",
            f"Wrote {dest}.\n\n"
            "Copy it to the target server if that's not this machine, then run:\n\n"
            f"    {run_instructions.format(dest=dest)}\n\n"
            "Review the script first -- it makes real system changes.",
        )
