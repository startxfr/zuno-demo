# Data Classification

| Class | External SaaS models | Default handling |
|---|---|---|
| C1 | Allowed | Standard routing policy |
| C2 | Restricted | Context filtering and policy validation required |
| C3 | Forbidden | Local inference only |

Confluence content is C2. Sovereign DAT content is C3/local-only for inference routing purposes.
