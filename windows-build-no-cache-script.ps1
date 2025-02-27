$folders = @(
        'pocket-app'
        'spreadsheet-app'
        'project-mgmt-app'
        'canvas-app'
        'interview-app'
        'english-text-stats-app'
        'learning-language-app'
        'shopping-stats-server-app'
        'my-tools-vaadin-app'
)

$anyFolderUpdated = $false

function Update-Folder {
    param (
        [string]$folderPath,
        [string]$folderName,
        [boolean]$forceRebuilt
    )

    Write-Host "Processing module: $folderName"

    Push-Location -Path $folderPath

    Write-Host "Pulling latest changes from Git in: $folderName"
    $gitOutput = git pull 2>&1

    if ($gitOutput -notmatch "Already up to date.") {
        Write-Host "Code has been updated in directory: $folderName"
        $script:anyFolderUpdated = $true

        Write-Host "Building Docker for: $folderName"
        docker build --no-cache -t $folderName .

        Pop-Location
        return $true
    } else {
        Write-Host "No changes in module: $folderName"
        if ($forceRebuilt) {
            Write-Host "But module will be rebuilt: $folderName"
            $script:anyFolderUpdated = $true
            Write-Host "Building Docker for: $folderName"
            docker build -t $folderName .

            Pop-Location
            return $true
        }

        Pop-Location
        return $false
    }
}


$bervanUtilsUpdated = Update-Folder -folderPath "bervan-utils" -folderName "bervan-utils"

if ($bervanUtilsUpdated) {
    Write-Host "bervan-utils has been updated, building common-vaadin..."
    $commonVaadinUpdated = Update-Folder -folderPath "common-vaadin" -folderName "common-vaadin" -forceRebuilt $true
} else {
    $commonVaadinUpdated = Update-Folder -folderPath "common-vaadin" -folderName "common-vaadin" -forceRebuilt $false
}

if ($commonVaadinUpdated) {
    Write-Host "common-vaadin has been rebuilt, building other modules..."
}

$fileStorageUpdated = Update-Folder -folderPath "file-storage-app" -folderName "file-storage-app" -forceRebuilt $commonVaadinUpdated

if ($fileStorageUpdated) {
    Write-Host "file-storage-app has been rebuilt, building streaming"
}

if($fileStorageUpdated -Or $commonVaadinUpdated) {
    Update-Folder -folderPath "streaming-platform-app" -folderName "streaming-platform-app" -forceRebuilt $true
} else {
    Update-Folder -folderPath "streaming-platform-app" -folderName "streaming-platform-app" -forceRebuilt $false
}

for ($i = 0; $i -lt $folders.Length; $i++) {
   Update-Folder -folderPath $folders[$i] -folderName $folders[$i] -forceRebuilt $commonVaadinUpdated
}

docker-compose --env-file .env_my_tools up --build -d

Write-Host "END"