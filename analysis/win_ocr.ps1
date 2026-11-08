param([string]$Dir,[string]$Out)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null=[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null=[Windows.Graphics.Imaging.BitmapDecoder,Windows.Foundation,ContentType=WindowsRuntime]
$null=[Windows.Storage.StorageFile,Windows.Foundation,ContentType=WindowsRuntime]
$null=[Windows.Storage.Streams.RandomAccessStream,Windows.Foundation,ContentType=WindowsRuntime]
$asTask=([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op,[Type]$t){ $m=$asTask.MakeGenericMethod($t); $task=$m.Invoke($null,@($op)); $task.Wait(-1)|Out-Null; $task.Result }
$engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if($null -eq $engine){ throw 'no OCR engine' }
$res=@{}
Get-ChildItem -Path $Dir -Filter *.png | Sort-Object Name | ForEach-Object {
  $f=Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($_.FullName)) ([Windows.Storage.StorageFile])
  $s=Await ($f.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
  $d=Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($s)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $b=Await ($d.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
  $r=Await ($engine.RecognizeAsync($b)) ([Windows.Media.Ocr.OcrResult])
  $lines=@(); foreach($l in $r.Lines){ $lines+=$l.Text }
  $res[$_.BaseName]=@{ lines=$lines; angle=$r.TextAngle }
  $s.Dispose()
}
$res | ConvertTo-Json -Depth 5 | Out-File -FilePath $Out -Encoding utf8
Write-Output ("OCR done: " + $res.Count + " files; lang=" + $engine.RecognizerLanguage.LanguageTag)
