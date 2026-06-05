; Loki NSIS Installer
!include "MUI2.nsh"

Name "Loki"
OutFile "Loki-Setup.exe"
InstallDir "$LOCALAPPDATA\Loki"
RequestExecutionLevel user

!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNCONFIRMPAGE
!insertmacro MUI_LANGUAGE "English"

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "dist\Loki\*.*"

  CreateDirectory "$SMPROGRAMS\Loki"
  CreateShortcut "$SMPROGRAMS\Loki\Loki.lnk" "$INSTDIR\Loki.exe"
  CreateShortcut "$DESKTOP\Loki.lnk" "$INSTDIR\Loki.exe"

  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "Loki" "$INSTDIR\Loki.exe"

  ; Note: Ollama and ffmpeg should be installed separately
  ; Run: ollama pull phi3:mini && ollama pull moondream

  Exec "$INSTDIR\Loki.exe"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\Loki.exe"
  RMDir /r "$INSTDIR"
  Delete "$SMPROGRAMS\Loki\Loki.lnk"
  Delete "$DESKTOP\Loki.lnk"
  RMDir "$SMPROGRAMS\Loki"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "Loki"
SectionEnd
