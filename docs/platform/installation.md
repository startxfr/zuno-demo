# Installation Workflow

The public operator interface is intentionally small, structured as Day 0
(cluster prerequisites) / Day 1 (build + run the platform) - ADR-0056:

```bash
make day0|d0 check [component]
make day0|d0 install [component]
make day0|d0 configure [component]
make day0|d0 all [component]        # check + install + configure, in order

make day1|d1 check [component]      # `agents` runs the ADR-0053 acceptance gate
make day1|d1 build [component]
make day1|d1 configure|run [component]
make day1|d1 all [component]
```

The Makefile dispatches implementation work to Ansible playbooks and roles.
