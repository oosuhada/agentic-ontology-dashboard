# Phase 18 — V4 Commercial Product Runtime

- Base commit: `9e6154b`
- Application route: `/app/projects/manufacturing-demo-project/blueprint-v4`
- Release policy: V4 is an independent application and is not the default Project route.

## Implemented

- versioned application registry for V1, V2, V3 and V4
- unique storage, query and collaboration namespaces per application version
- lazy-loaded V4 route and an application-level error boundary
- manifest-driven V4 navigation, Project/Dataset/role context and readiness taxonomy
- real launch paths to existing Object, Analysis, Model and Governance workbenches
- accurate `planned` states for Phase 27, 28 and 32 capabilities instead of simulated success
- safe protected-route return URL through login
- desktop and mobile V4 layout

V1, V2 and V3 routing and application components remain unchanged. Shared authentication and
Project boundary improvements apply to all versions without redirecting them to V4.
