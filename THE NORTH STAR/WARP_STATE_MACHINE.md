# WARP State Machine

## Purpose

This document defines the states of the WARP process.

It does not describe implementation.

It defines the valid progression of materialization.

------------------------------------------------------------------------

## States

### LIVE

Normal working state.

Ideas may emerge. No materialization takes place.

------------------------------------------------------------------------

### WARP_STARTED

The decision to begin WARP has been made.

No new development begins from this point.

------------------------------------------------------------------------

### ANALYSING

Collected knowledge is reviewed.

Potential canonical insights are identified.

------------------------------------------------------------------------

### CLASSIFYING

Each confirmed insight is assigned to its destination.

Existing canonical documents are preferred.

------------------------------------------------------------------------

### MATERIALISING

Approved knowledge is written into Atlas.

No verification takes place yet.

------------------------------------------------------------------------

### VERIFYING

Atlas is checked for consistency.

Verification includes:

-   required documents updated
-   no confirmed insight left only in chat
-   no contradictory canonical knowledge
-   current state documented

If verification fails, WARP returns to MATERIALISING.

------------------------------------------------------------------------

### SAVING

Atlas is secured.

Examples include:

-   review changes
-   prepare commit
-   create backup if required

------------------------------------------------------------------------

### ATLAS_SYNCHRON

Materialization is complete.

Atlas no longer depends on the current conversation.

The system returns to LIVE.
