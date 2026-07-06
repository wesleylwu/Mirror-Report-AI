$images = @(
    "../input/IMG_9688.JPG",
    "../input/IMG_9689.JPG",
    "../input/IMG_9691.JPG",
    "../input/IMG_9692.JPG",
    "../input/IMG_9693.JPG",
    "../input/IMG_9697.JPG"
)

foreach ($img in $images) {
    $base = [System.IO.Path]::GetFileNameWithoutExtension($img)
    $out  = "../output/$base.json"
    Write-Host "Processing $img -> $out"
    python JSONgen.py $img $out
}
