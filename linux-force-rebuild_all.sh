#!/bin/bash

# List of folders
folders=(
    common-vaadin
    pocket-app
    spreadsheet-app
    project-mgmt-app
    canvas-app
    streaming-platform-app
    interview-app
    english-text-stats-app
    file-storage-app
    learning-language-app
    shopping-stats-server-app
)

# Iterate through each folder
for folderName in "${folders[@]}"; do
    echo "Building Docker image for folder: $folderName"
    
    # Navigate into the folder
    cd "$folderName" || { echo "Failed to navigate into folder $folderName"; exit 1; }
    
    # Build the Docker image
    docker build --no-cache -t "$folderName" .
    
    # Navigate back to the parent folder
    cd ..
    
    echo "Docker image for $folderName has been built."
done

echo "All Docker images have been built successfully."