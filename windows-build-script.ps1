$folders = @(
        'pocket-app'
        'spreadsheet-app'
        'project-mgmt-app'
        'canvas-app'
        'streaming-platform-app'
        'interview-app'
        'english-text-stats-app'
        'file-storage-app'
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

    Set-Location -Path $folderPath

    $gitOutput = git pull 2>&1

    if ($gitOutput -notmatch "Already up to date.") {
        Write-Host "Code has been updated in directory: $folderName"
        $script:anyFolderUpdated = $true

        Write-Host "Building Docker for: $folderName"
        docker build --no-cache -t $folderName .

        return $true
    } else {
        Write-Host "No changes in module: $folderName"
        if ($forceRebuilt) {
            Write-Host "But module will be rebuilt: $folderName"
            $script:anyFolderUpdated = $true
            Write-Host "Building Docker for: $folderName"
            docker build --no-cache -t $folderName .
            return $true
        }
        return $false
    }
}

$bervanUtilsUpdated = Update-Folder -folderPath "bervan-utils" -folderName "bervan-utils"

if ($bervanUtilsUpdated) {
    Write-Host "bervan-utils has been updated, building common-vaadin..."
    $commonVaadinUpdated = Update-Folder -folderPath "common-vaadin" -folderName "common-vaadin" -forceRebuilt true
} else {
    $commonVaadinUpdated = Update-Folder -folderPath "common-vaadin" -folderName "common-vaadin" -forceRebuilt false
}

if ($commonVaadinUpdated) {
    Write-Host "common-vaadin has been rebuilt, building other modules..."
}

for ($i = 0; $i -lt $folders.Length; $i++) {
   Update-Folder -folderPath $folders[$i] -folderName $folders[$i] -forceRebuilt $commonVaadinUpdated
}

if ($anyFolderUpdated) {
    Write-Host "At least 1 folder rebuilt, building my-tools-vaadin-app..."
}

Update-Folder -folderPath "my-tools-vaadin-app" -folderName "my-tools-vaadin-app" -forceRebuilt $anyFolderUpdated

docker-compose --env-file .env_my_tools up --build -d

Write-Host "END"