# Features

This directory contains isolated bot features that can be enabled or disabled independently.

Design considerations:
- A feature should be implemented in a single file
- Translatable strings and feature settings should have `FEATURE_` prefix, where FEATURE is the name of the feature
- A feature should have `init()` and `post_init()` functions that will be called from the main program.  If the feature is disabled, those functions should return early, before initialising data or adding any handlers to the application.  
- Feature-related data should be stored in the `resources` sub-directory