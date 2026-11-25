@echo off
rem Builds pairing_test.exe with the C# compiler that ships with Windows. Nothing is downloaded.
setlocal
set FW=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319
set MD=%WINDIR%\System32\WinMetadata
"%FW%\csc.exe" /nologo /optimize /platform:x64 /out:"%~dp0pairing_test.exe" ^
  /r:"%MD%\Windows.Foundation.winmd" /r:"%MD%\Windows.Devices.winmd" /r:"%MD%\Windows.Storage.winmd" ^
  /r:"%FW%\System.Runtime.dll" /r:"%FW%\System.Runtime.InteropServices.WindowsRuntime.dll" ^
  "%~dp0pairing_test.cs"
