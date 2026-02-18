#!/bin/bash

set -e

initial_dir=$(pwd)

git pull

folders="bervan-utils common-vaadin file-storage-app pocket-app spreadsheet-app invest-track-app project-mgmt-app cook-book canvas-app streaming-platform-app interview-app english-text-stats-app learning-language-app shopping-stats-server-app my-tools-vaadin-app"

for folder in $folders; do
  if [ -d "$folder" ]; then
    cd "$folder"
    echo "Processing folder: $folder"
    git stash
    git pull
    if [ "$folder" == "bervan-utils" ]; then
      docker build -t bervan-utils .
    fi
    cd ..
  else
    echo "Folder not found: $folder"
  fi
done

cd "$initial_dir"
docker-compose --env-file .env_my_tools up --build -d