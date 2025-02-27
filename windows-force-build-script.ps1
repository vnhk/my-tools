$folders = @(
        'bervan-utils'
        'common-vaadin'
        'file-storage-app'
        'pocket-app'
        'spreadsheet-app'
        'project-mgmt-app'
        'canvas-app'
        'streaming-platform-app'
        'interview-app'
        'english-text-stats-app'
        'learning-language-app'
        'shopping-stats-server-app'
)

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
            docker build --no-cache -t $folderName .

            Pop-Location
            return $true
        }

        Pop-Location
        return $false
    }
}

for ($i = 0; $i -lt $folders.Length; $i++) {
   Update-Folder -folderPath $folders[$i] -folderName $folders[$i] -forceRebuilt $true
}

docker-compose --env-file .env_my_tools up --build -d

Write-Host "END"