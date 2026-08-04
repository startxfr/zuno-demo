# Installation Workflow

The public operator interface is intentionally small:

```bash
make precheck
make precheck <component>
make prepare
make prepare <component>
make configure
make configure <scope>
make install
make check
```

The Makefile dispatches implementation work to Ansible playbooks and roles.
