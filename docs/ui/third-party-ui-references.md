# UI reference and license notes

This document records external projects consulted while designing the dashboard UI. It is supporting design provenance, not an application entry point or generated build artifact.

## Scope of use

The implementation in `systems/frontend/src/ui/foundry/` is an original adaptation for this repository. It reuses interaction patterns, information architecture, and public design-system concepts. It does not include Palantir proprietary HTML, CSS, images, fonts, icons, trademarks, or application source code.

## Palantir Blueprint

- Upstream project: Palantir Blueprint
- License: Apache License 2.0
- Use in this repository: existing `@blueprintjs/*` packages and public Blueprint component/density conventions.

## mini_foundry_public

- License: MIT
- Copyright: Copyright (c) 2026 Abdullrahman Bahar
- Files reviewed: dashboard canvas, component palette, data table, ontology graph, theme and global style definitions.
- Adaptation: compact board frame composition, small-radius surfaces, dense rows, explicit object-node metadata, and fixed-rail workbench structure. No source file was copied verbatim.

## openfoundry-emulator

- License: Apache License 2.0
- Files reviewed: Contour page, data table, application shell CSS, widget registry, and UI tokens.
- Adaptation: registry-oriented board definitions, pane-based workbench composition, semantic token naming, and table/empty-state conventions. No source file was copied verbatim.

## contour-translation

- License: MIT
- Copyright: Copyright (c) 2026 Sibyl Advisory
- Use in this repository: interaction and terminology reference for Contour-style analysis flows only. No source file or asset was copied verbatim.

## Excluded material

The unlicensed `palantir-ui` mirror and Palantir production website markup/assets were not copied or bundled. Public Palantir documentation was used only as behavioral and visual reference.
