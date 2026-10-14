---
name: file-storage-manager
description: >-
  Enforces and guides saving and managing files and directories on disk via FileServiceManager,
  FileDiskStorageService, and FileDBStorageService across all backend modules. Use this skill whenever
  implementing or modifying file storage, file uploads, disk writes, directory creation, or file metadata
  management in backend Java services.
---

# Backend File Storage Skill

This skill defines mandatory patterns and guidelines for reading, writing, updating, and deleting files and directories across all backend modules in the repository (`streaming-platform-app`, `file-storage-app`, `pocket-app`, etc.).

---

## 1. Core Rule: FileServiceManager Mandatory

> [!IMPORTANT]
> **Never write application files or directories directly to disk using `Files.write`, `Files.copy`, `new FileOutputStream`, or `new File().mkdirs()` when persisting application data.**
> All managed application storage operations must go through `com.bervan.filestorage.service.FileServiceManager` (and its supporting services `FileDiskStorageService` and `FileDBStorageService`), unless the operation falls under a documented exception.

---

## 2. Permitted Exceptions

Direct filesystem operations (`Files.*`, `File.*`) are **only** permitted in the following specific scenarios where `FileServiceManager` does not provide an API:

1. **Short-lived scratch/temp files**:
   - Temporary extraction directories (e.g. `Files.createTempDirectory("zip_extract_")` or `Files.createTempFile(...)`) used for processing or unzipping, provided they are cleaned up in a `finally` block.
2. **Third-party in-place file manipulation**:
   - Libraries that require a physical `java.io.File` on disk (e.g. `Mp3File` from `mp3agic` for editing ID3 tags). The file must first be saved via `FileServiceManager`, then resolved via `fileDiskStorageService.getFile(...)`, modified, and any resulting size changes must update the `Metadata` entity.
3. **Directory scanning for initial synchronization**:
   - Reading existing files on startup or disk reload (`Files.list`, `Files.walk`), followed by registering missing records via `ensureDirectoryMetadata` or `ensureTrackMetadata`.

---

## 3. Key Services & Responsibilities

| Service | Package | Responsibility |
| :--- | :--- | :--- |
| **`FileServiceManager`** | `com.bervan.filestorage.service` | High-level facade for business modules: saves files with DB metadata, creates directories with metadata, handles cascading deletions, loads by path. |
| **`FileDiskStorageService`** | `com.bervan.filestorage.service` | Physical disk storage, handles folder mappings (`file.service.storage.folders.mapping`, automapping), resolves absolute `Path` on disk via `getFile(relativePath)`, overwrites files via `overwriteFile(path, bytes)`, moves directories via `moveFile(source, dest)`. |
| **`FileDBStorageService`** | `com.bervan.filestorage.service` | Direct database metadata access (`Metadata` entity): `loadByPathAndFilename(path, filename)`, `store(...)`, `update(...)`, `createEmptyDirectory(...)`. |

---

## 4. Path Formatting Conventions

1. **Relative storage paths** always start with `/` and subdirectories are delimited by `/`.
   - Example root: `/Audio Library` or `/Streaming Platform`.
2. **Metadata paths (`Metadata.path`) always end with `/`**:
   - Example: `/Audio Library/Ludwig van Beethoven/Symphony No. 9 (1824)/`
   - Use a helper to enforce this:
     ```java
     private String ensureStoragePathEndsWithSlash(String path) {
         if (path == null || path.isBlank()) return "/";
         return path.endsWith("/") ? path : path + "/";
     }
     ```
3. **Resolving physical disk path**:
   - Never do `baseDir.resolve(...)` with raw hardcoded string paths.
   - Use `fileDiskStorageService.getFile(relativePath)` which respects `file.service.storage.folder.main` and folder mappings.

---

## 5. Standard Implementation Patterns

### Pattern A: Saving or Updating In-Memory Data / Generated Files

When saving JSON metadata (`details.json`, `album.json`), playlists (`playlist.m3u8`), or extracted covers:
> [!WARNING]
> `FileDiskStorageService.store()` appends `(1)`, `(2)` to the filename if the file already exists on disk.
> To prevent duplicate files, always check if metadata already exists in DB. If it does, overwrite in place via `fileDiskStorageService.overwriteFile()`.

```java
private void saveOrUpdateFile(String filename, byte[] content, String contentType,
                              String description, String storagePath, Path dir) {
    String cleanStoragePath = ensureStoragePathEndsWithSlash(storagePath);
    Metadata existingMeta = null;
    try {
        List<Metadata> found = fileDBStorageService.loadByPathAndFilename(cleanStoragePath, filename);
        if (!found.isEmpty()) {
            existingMeta = found.get(0);
        }
    } catch (Exception e) {
        log.warn("Could not check existing metadata for {} in {}: {}", filename, cleanStoragePath, e.getMessage());
    }

    if (existingMeta != null) {
        Path targetFile = dir.resolve(filename);
        fileDiskStorageService.overwriteFile(targetFile, content);
        existingMeta.setFileSize((long) content.length);
        existingMeta.setModificationDate(LocalDateTime.now());
        fileServiceManager.updateMetadata(existingMeta);
    } else {
        // Remove stray file on disk if exists to prevent FileDiskStorageService from creating filename(1).ext
        try {
            Files.deleteIfExists(dir.resolve(filename));
        } catch (Exception ignored) {}

        BervanMockMultiPartFile mockFile = new BervanMockMultiPartFile(
                filename, filename, contentType, new ByteArrayInputStream(content)
        );
        fileServiceManager.save(mockFile, description, cleanStoragePath);
    }
}
```

### Pattern B: Directory Creation

Always create both the physical directory and the `Metadata` record in the database:

```java
String rootStoragePath = ensureStoragePathEndsWithSlash(getModuleRelativePath());
String folderName = sanitizeFileName(name);

Path dir = getModuleRoot().resolve(folderName);
if (!Files.exists(dir)) {
    fileServiceManager.createEmptyDirectory(rootStoragePath, folderName);
} else {
    // If physical directory already existed, ensure DB metadata is registered
    ensureDirectoryMetadata(rootStoragePath, folderName);
}
```

### Pattern C: File Uploads (`MultipartFile`)

When handling user uploads:

```java
// Check and clean up existing metadata / file if replacing
String cleanStoragePath = ensureStoragePathEndsWithSlash(targetStoragePath);
List<Metadata> existing = fileDBStorageService.loadByPathAndFilename(cleanStoragePath, sanitizedFilename);
for (Metadata m : existing) {
    fileServiceManager.delete(m);
}

// Save via FileServiceManager
BervanMockMultiPartFile filePart = new BervanMockMultiPartFile(
        sanitizedFilename, sanitizedFilename, file.getContentType(), new ByteArrayInputStream(file.getBytes())
);
fileServiceManager.save(filePart, description, cleanStoragePath);
```

### Pattern D: Deletion

Deleting a file or folder must remove both the database `Metadata` and the disk contents:

```java
// For a single file:
List<Metadata> metaList = fileDBStorageService.loadByPathAndFilename(storagePath, filename);
for (Metadata m : metaList) {
    fileServiceManager.delete(m); // deletes DB metadata and calls fileDiskStorageService.delete(...)
}

// For a directory:
// fileServiceManager.delete(folderMetadata) cascades delete to all child metadata in DB
List<Metadata> folderMeta = fileDBStorageService.loadByPathAndFilename(parentStoragePath, folderName);
for (Metadata m : folderMeta) {
    fileServiceManager.delete(m);
}
```

### Pattern E: Moving / Renaming Folders

When renaming or moving an existing directory:

```java
// Move physical folder on disk
fileDiskStorageService.moveFile(oldDir, newDir);

// Migrate Metadata path records in database
Set<Metadata> oldMeta = fileDBStorageService.loadByPath(oldStoragePath);
if (oldMeta != null) {
    for (Metadata m : oldMeta) {
        m.setPath(newStoragePath);
        fileServiceManager.updateMetadata(m);
    }
}

// Update directory metadata itself
List<Metadata> dirMeta = fileDBStorageService.loadByPathAndFilename(oldParentStoragePath, oldFolderName);
for (Metadata m : dirMeta) {
    m.setPath(newParentStoragePath);
    m.setFilename(newFolderName);
    fileServiceManager.updateMetadata(m);
}
```

---

## 6. Checklist for New / Modified Services

When creating or editing a service that interacts with disk files:
- [ ] Injected `FileServiceManager`, `FileDiskStorageService`, and `FileDBStorageService` instead of hardcoded paths.
- [ ] Root storage directory configured via `@Value("${...file-storage-relative-path}")`.
- [ ] Directory creation done via `fileServiceManager.createEmptyDirectory(...)`.
- [ ] Files saved via `fileServiceManager.save(...)` or `saveOrUpdateFile(...)`.
- [ ] Avoided duplicate `(1)` files by checking DB metadata before writing.
- [ ] Deletions executed via `fileServiceManager.delete(metadata)`.
