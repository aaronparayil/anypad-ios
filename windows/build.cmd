@echo off
rem Builds controller.exe (terminal) and AnyPad.exe (window, one self-contained file)
rem with the C# compiler that ships with Windows. Nothing is downloaded.
setlocal
set FW=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319
set MD=%WINDIR%\System32\WinMetadata
set REFS=/r:"%MD%\Windows.Foundation.winmd" /r:"%MD%\Windows.Devices.winmd" /r:"%FW%\System.Runtime.dll" /r:"%FW%\System.Runtime.InteropServices.WindowsRuntime.dll" /r:System.Management.dll
"%FW%\csc.exe" /nologo /optimize /platform:x64 /out:"%~dp0controller.exe" %REFS% "%~dp0controller.cs" "%~dp0Pads.cs" || exit /b 1
"%FW%\csc.exe" /nologo /optimize /platform:x64 /target:winexe /main:Gui /out:"%~dp0AnyPad.exe" %REFS% ^
  /win32icon:"%~dp0AnyPad.ico" /win32manifest:"%~dp0AnyPad.manifest" ^
  /resource:"%~dp0in_wsl.sh",in_wsl.sh /resource:"%~dp0..\linux\relay.py",relay.py /resource:"%~dp0..\linux\pairing_test.py",pairing_test.py ^
  /resource:"%~dp0..\assets\logo.png",logo.png ^
  "%~dp0AnyPad.cs" "%~dp0AnyPadUi.cs" "%~dp0controller.cs" "%~dp0Pads.cs" || exit /b 1
