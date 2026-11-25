@echo off
rem Builds controller.exe with the C# compiler that ships with Windows. Nothing is downloaded.
setlocal
set FW=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319
set MD=%WINDIR%\System32\WinMetadata
"%FW%\csc.exe" /nologo /optimize /platform:x64 /out:"%~dp0controller.exe" ^
  /r:"%MD%\Windows.Foundation.winmd" /r:"%MD%\Windows.Devices.winmd" ^
  /r:"%FW%\System.Runtime.dll" /r:"%FW%\System.Runtime.InteropServices.WindowsRuntime.dll" ^
  /r:System.Management.dll ^
  "%~dp0controller.cs"
