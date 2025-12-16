# Features

## Feature index

This module contains isolated bot features.

**<a href="services/README.md">Services</a>** is the core feature that manages the user directory.  It cannot be disabled.

### Optional features

**Antispam** detects and deletes spam messages

**Glossary** maintains an explanatory dictionary for a set of specific words that are used in the community but can be confusing to newcomers.  The feature detects such words in the discussion, highlights messages where these words are found, and can provide explanations.

**<a href="moderation/README.md">Moderation</a>** implements public-driven moderation that aims at making the community self-regulated

## Design considerations

- A feature should be implemented in a single file or as a submodule
- Translatable strings and feature settings should have `FEATURE_` prefix, where FEATURE is the name of the feature
- A feature should have `init()` and `post_init()` functions that will be called from the main program.  If the feature is disabled, those functions should return early, before initialising data or adding any handlers to the application.  
- Should the feature store persistent data in files, these files should reside in the `resources` subdirectory, and their names should have `feature_` prefix, where `feature` is the name of the feature

