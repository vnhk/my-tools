@echo off
setlocal

set "initial_dir=%CD%"

set "folders=bervan-utils common-vaadin file-storage-app pocket-app spreadsheet-app project-mgmt-app canvas-app streaming-platform-app interview-app english-text-stats-app learning-language-app shopping-stats-server-app my-tools-vaadin-app"

for %%f in (%folders%) do (
  if exist "%%f" (
    cd "%%f"
    echo Processing folder: %%f
    git stash
    git pull
    if "%%f"=="bervan-utils" (
      docker build -t bervan-utils .
    )
    cd ..
  ) else (
    echo Folder not found: %%f
  )
)

cd "%initial_dir%"
docker-compose --env-file .env_my_tools up --build -d

endlocal