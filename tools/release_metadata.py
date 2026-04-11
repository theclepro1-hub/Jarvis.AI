from __future__ import annotations

import argparse
import sys
from pathlib import Path
from string import Template


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.app_identity import (  # noqa: E402
    WINDOWS_APP_DESCRIPTION,
    WINDOWS_APP_DISPLAY_NAME,
    WINDOWS_APP_USER_MODEL_ID,
    WINDOWS_EXECUTABLE_NAME,
    WINDOWS_INSTANCE_MUTEX,
    WINDOWS_INSTALLER_APP_ID,
    WINDOWS_PUBLISHER,
    WINDOWS_REPOSITORY_URL,
    WINDOWS_SETUP_MUTEX,
    WINDOWS_SUPPORT_URL,
    WINDOWS_UPDATES_URL,
)
from core.version import DEFAULT_VERSION  # noqa: E402


INSTALLER_TEMPLATE = Template(
    r"""[Setup]
AppId=$app_id
AppName=$display_name
AppVersion=$version
AppVerName=$display_name $version
AppPublisher=$publisher
AppPublisherURL=$publisher_url
AppSupportURL=$support_url
AppUpdatesURL=$updates_url
DefaultDirName={autopf}\$display_name
DefaultGroupName=$display_name
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\$executable_name
UninstallDisplayName=$display_name
AppMutex=$instance_mutex
SetupMutex=$setup_mutex
CloseApplications=yes
CloseApplicationsFilter=$executable_name
RestartApplications=yes
VersionInfoCompany=$publisher
VersionInfoDescription=$description
VersionInfoProductName=$display_name
VersionInfoProductVersion=$version
VersionInfoVersion=$version.0
VersionInfoTextVersion=$version
OutputDir=$release_dir
OutputBaseFilename=JarvisAi_Unity_${version}_windows_installer
SetupIconFile=$icon_path
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UsePreviousAppDir=yes
UsePreviousLanguage=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "$portable_dist_path\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Icons]
Name: "{group}\$display_name"; Filename: "{app}\$executable_name"; AppUserModelID: "$app_user_model_id"
Name: "{group}\Uninstall $display_name"; Filename: "{uninstallexe}"
Name: "{autodesktop}\$display_name"; Filename: "{app}\$executable_name"; Tasks: desktopicon; AppUserModelID: "$app_user_model_id"

[Run]
Filename: "{app}\$executable_name"; Description: "{cm:LaunchProgram,$display_name}"; Flags: nowait postinstall skipifsilent
"""
)


def render_installer_script(
    *,
    version: str = DEFAULT_VERSION,
    release_dir: str,
    icon_path: str,
    portable_dist_path: str,
) -> str:
    return INSTALLER_TEMPLATE.substitute(
        app_id=WINDOWS_INSTALLER_APP_ID,
        app_user_model_id=WINDOWS_APP_USER_MODEL_ID,
        description=WINDOWS_APP_DESCRIPTION,
        display_name=WINDOWS_APP_DISPLAY_NAME,
        executable_name=WINDOWS_EXECUTABLE_NAME,
        icon_path=icon_path,
        instance_mutex=WINDOWS_INSTANCE_MUTEX,
        portable_dist_path=portable_dist_path,
        publisher=WINDOWS_PUBLISHER,
        publisher_url=WINDOWS_REPOSITORY_URL,
        release_dir=release_dir,
        setup_mutex=WINDOWS_SETUP_MUTEX,
        support_url=WINDOWS_SUPPORT_URL,
        updates_url=WINDOWS_UPDATES_URL,
        version=version,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the JARVIS Unity installer script.")
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument("--release-dir", required=True)
    parser.add_argument("--icon-path", required=True)
    parser.add_argument("--portable-dist-path", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_installer_script(
            version=args.version,
            release_dir=args.release_dir,
            icon_path=args.icon_path,
            portable_dist_path=args.portable_dist_path,
        ),
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
