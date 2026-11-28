@echo off
rem Builds controller.exe (terminal) and the two windowed apps, AnyPad-iOS.exe and
rem AnyPad-Android.exe (each one self-contained file), with the C# compiler that ships
rem with Windows. Nothing is downloaded. The two apps differ only in their words.
setlocal
rem Inside :app, %~dp0 would name the label, so keep the folder here.
set D=%~dp0
set FW=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319
set MD=%WINDIR%\System32\WinMetadata
set REFS=/r:"%MD%\Windows.Foundation.winmd" /r:"%MD%\Windows.Devices.winmd" /r:"%FW%\System.Runtime.dll" /r:"%FW%\System.Runtime.InteropServices.WindowsRuntime.dll" /r:System.Management.dll
"%FW%\csc.exe" /nologo /optimize /platform:x64 /out:"%D%controller.exe" %REFS% "%D%controller.cs" "%D%Pads.cs" "%D%Target.cs" || exit /b 1
call :app AnyPad-iOS.exe || exit /b 1
call :app AnyPad-Android.exe /define:ANDROID || exit /b 1
exit /b 0

:app
"%FW%\csc.exe" /nologo /optimize /platform:x64 /target:winexe /main:Gui /out:"%D%%1" %2 %REFS% ^
  /win32icon:"%D%AnyPad.ico" /win32manifest:"%D%AnyPad.manifest" ^
  /resource:"%D%in_wsl.sh",in_wsl.sh /resource:"%D%..\linux\relay.py",relay.py /resource:"%D%..\linux\pairing_test.py",pairing_test.py ^
  /resource:"%D%..\assets\logo.png",logo.png ^
  "%D%AnyPad.cs" "%D%AnyPadUi.cs" "%D%controller.cs" "%D%Pads.cs" "%D%Target.cs"
exit /b %errorlevel%
