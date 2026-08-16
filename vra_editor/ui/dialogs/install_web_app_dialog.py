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
        self.ldap_server_edit: QLineEdit | None = None
        self.ldap_bind_pattern_edit: QLineEdit | None = None
        self.ldap_use_ssl_check: QCheckBox | None = None

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

        outer.addWidget(self._build_ldap_group())

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

    def _build_ldap_group(self) -> QGroupBox:
        group = QGroupBox("LDAP (for web login)")
        form = QFormLayout(group)

        self.ldap_server_edit = QLineEdit()
        self.ldap_server_edit.setPlaceholderText("ldap://ldap.yourarchive.org:389")
        form.addRow("Server:", self.ldap_server_edit)

        self.ldap_bind_pattern_edit = QLineEdit()
        self.ldap_bind_pattern_edit.setPlaceholderText("cn={username},ou=people,dc=example,dc=org")
        self.ldap_bind_pattern_edit.setToolTip(
            "A bind DN template -- {username} is replaced with whatever the cataloguer types at "
            "the web login form. Use '{username}@example.org' or 'EXAMPLE\\\\{username}' for "
            "Active Directory's UPN/NetBIOS forms instead."
        )
        form.addRow("Bind pattern:", self.ldap_bind_pattern_edit)

        self.ldap_use_ssl_check = QCheckBox()
        form.addRow("Use SSL/TLS to LDAP:", self.ldap_use_ssl_check)

        return group

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------

    def _selected_proxy(self, group: QButtonGroup) -> str:
        checked = group.checkedButton()
        return checked.property('proxy_value') if checked else 'none'

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
        ldap_server = self.ldap_server_edit.text().strip()
        ldap_bind_pattern = self.ldap_bind_pattern_edit.text().strip()
        reverse_proxy = self._selected_proxy(self.proxy_group)

        port = self._parse_port(self.port_edit.text().strip())
        if port is None:
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
        if not ldap_server:
            missing.append("LDAP server")
        if not ldap_bind_pattern:
            missing.append("LDAP bind pattern")
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
        ldap_server = self.ldap_server_edit.text().strip()
        ldap_bind_pattern = self.ldap_bind_pattern_edit.text().strip()
        reverse_proxy = self._selected_proxy(self.win_proxy_group)

        port = self._parse_port(self.win_port_edit.text().strip())
        if port is None:
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
        if not ldap_server:
            missing.append("LDAP server")
        if not ldap_bind_pattern:
            missing.append("LDAP bind pattern")
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
            run_instructions="Right-click {dest} and \"Run with PowerShell\" as Administrator, "
                              "or from an elevated PowerShell prompt: powershell -ExecutionPolicy "
                              "Bypass -File {dest}",
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
