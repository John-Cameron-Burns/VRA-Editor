import getpass

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QCheckBox, QPushButton,
    QRadioButton, QButtonGroup, QLabel, QFileDialog, QMessageBox, QGroupBox,
)

from ...config import DEFAULT_CONFIG_PATH
from ...core.web_installer import BundleMissingError, InstallOptions, generate_install_script


# noinspection PyUnresolvedReferences
class InstallWebAppDialog(QDialog):
    """Generates a self-contained install script for the web companion
    app (Linux only) -- see core/web_installer.py for what the script
    actually does. This dialog itself makes no system changes and
    needs no elevated privileges: it only writes the generated .sh
    file wherever the user chooses to save it. The user reviews and
    runs that script themselves with sudo.

    Usage:
        dlg = InstallWebAppDialog(parent=self)
        dlg.exec()
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Install Web Companion")
        self.setModal(True)
        self.resize(520, 480)

        self.install_dir_edit: QLineEdit | None = None
        self.port_edit: QLineEdit | None = None
        self.service_user_edit: QLineEdit | None = None
        self.config_path_edit: QLineEdit | None = None
        self.proxy_group: QButtonGroup | None = None
        self.server_name_edit: QLineEdit | None = None
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
            "Generates a script that deploys this web companion app as a systemd service on a "
            "Linux machine, with a reverse proxy in front of it. Review the script before "
            "running it -- it makes real system changes, and needs sudo. "
            "<b>TLS/certificates are not configured</b> -- set those up on your reverse proxy "
            "separately."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #444;")
        outer.addWidget(intro)

        outer.addWidget(self._build_deployment_group())
        outer.addWidget(self._build_proxy_group())
        outer.addWidget(self._build_ldap_group())

        generate_btn = QPushButton("Generate Install Script...")
        generate_btn.clicked.connect(self._on_generate)
        outer.addWidget(generate_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        outer.addWidget(close_btn)

    def _build_deployment_group(self) -> QGroupBox:
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

    def _build_proxy_group(self) -> QGroupBox:
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

    def _selected_proxy(self) -> str:
        checked = self.proxy_group.checkedButton()
        return checked.property('proxy_value') if checked else 'none'

    def _on_generate(self):
        install_dir = self.install_dir_edit.text().strip()
        config_path = self.config_path_edit.text().strip()
        service_user = self.service_user_edit.text().strip()
        server_name = self.server_name_edit.text().strip()
        ldap_server = self.ldap_server_edit.text().strip()
        ldap_bind_pattern = self.ldap_bind_pattern_edit.text().strip()
        reverse_proxy = self._selected_proxy()

        port_text = self.port_edit.text().strip()
        if not port_text.isdigit():
            QMessageBox.warning(self, "Invalid port", "Port must be a number.")
            return
        port = int(port_text)

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
            QMessageBox.critical(
                self, "Web app bundle not found",
                f"{e}\n\nThis usually means this build wasn't packaged with the web companion "
                "bundle -- rebuild via packaging/VRA_Editor.spec.",
            )
            return

        dest, _filter = QFileDialog.getSaveFileName(
            self, "Save install script", "install-vra-web.sh", "Shell scripts (*.sh)",
        )
        if not dest:
            return

        try:
            with open(dest, 'wb') as f:
                f.write(script)
            try:
                import os
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
            f"    sudo bash {dest}\n\n"
            "Review the script first -- it installs packages (with your confirmation), writes a "
            "systemd service, and (if a reverse proxy was chosen) a site config for it.",
        )
