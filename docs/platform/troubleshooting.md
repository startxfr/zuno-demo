# Troubleshooting

Troubleshooting procedures will be expanded as implementation proceeds. The first diagnostic entry point is `make day1|d1 check agents` (the ADR-0053 acceptance/security gate) plus component-specific Ansible role diagnostics (`make day0|d0 check [component]`, `make day1|d1 check [component]`). To roll back a misbehaving component, `make day0|d0 uninstall [component]` / `make day1|d1 uninstall [component]` reverse the install in the reverse dependency order.
