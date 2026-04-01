from ..diagnostics_tools import DiagnosticsToolsMixin


def build_diagnostics_settings_section(self, parent):
    return DiagnosticsToolsMixin._create_diagnostic_tab(self, parent)
