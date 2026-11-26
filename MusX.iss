[Setup]
AppName=MusX Space 2.0
AppVersion=0.1.0
DefaultDirName={localappdata}\Programs\MusX Space 2
DefaultGroupName=MusX Space 2
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
OutputDir=..\release
OutputBaseFilename=MusX-Space-Setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\MusX-Space.exe

[Files]
Source: "..\dist\MusX-Space.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\MusX Space 2"; Filename: "{app}\MusX-Space.exe"
