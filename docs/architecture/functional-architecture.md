# Functional Architecture

```mermaid
flowchart LR
    U[Internal User] --> P[Agent Portal]
    P --> C[Comage]
    P --> T[Tekos]
    P --> A[Arkos]
    P --> V[Advantage]
    P --> F[Finage]

    C --> Sales[(Sales Data)]
    C --> Mail[Gmail]
    T --> Docs[Official Documentation]
    T --> Conf[Confluence]
    A --> Docs
    A --> Conf
    A --> Drive[Google Drive / Docs]
    V --> Sales
    F --> Sales
```
