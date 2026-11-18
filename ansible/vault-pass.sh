#!/usr/bin/env bash
# Vault passphrase provider for ansible.cfg (vault_password_file). Prints the passphrase of the
# ansible-vault encrypted ansible/confidential.yml, read from ~/.config/zuno/vault-pass (mode 0600,
# outside the repository; override the path with ZUNO_VAULT_PASS_FILE).
#
# It never fails: ansible-playbook reads this at startup even when no vault file is involved, so a
# missing passphrase file (fresh clone, CI, AAP) must not stop an unencrypted checkout. When the file is
# absent a placeholder is printed; an encrypted file then fails to decrypt with Ansible's own clear
# error, which is the right outcome.
set -u
f="${ZUNO_VAULT_PASS_FILE:-$HOME/.config/zuno/vault-pass}"
if [ -r "$f" ]; then
  head -n 1 "$f"
else
  echo "zuno-no-vault-passphrase-configured"
fi
