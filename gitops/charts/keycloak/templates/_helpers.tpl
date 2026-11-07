{{- /*
ADR-0352/WP-211: the projected `sources` of the Keycloak file-vault SPI (${vault.<key>} placeholders
of files/realm-zuno.json resolve from files named zuno_<key with every "_" doubled>). Shared by the
built-in Keycloak pod (templates/keycloak.yaml) and, in external mode, by the reconcile Job, which
substitutes the same placeholders itself because an external Keycloak has no such SPI.
*/ -}}
{{- define "keycloak.vaultSources" -}}
- secret:
    name: {{ .Values.googleOAuthSecretName }}
    optional: true
    items:
      - key: client_id
        path: zuno_google__client__id
      - key: client_secret
        path: zuno_google__client__secret
{{- /* WP-190 phase 4: one item per experience client of .Values.experienceClients; the
       file name is zuno_<key with every "_" doubled>, key = <name with "-" as "_">_client_secret. */}}
{{- range .Values.experienceClients }}
{{- $key := printf "%s_client_secret" (.name | replace "-" "_") }}
- secret:
    # ${vault.{{ $key }}}, ADR-0562, ADR-0588, ADR-0589/0590.
    name: {{ .name }}-client-secret
    optional: true
    items:
      - key: client_secret
        path: {{ printf "zuno_%s" ($key | replace "_" "__") }}
{{- end }}
- secret:
    name: demo-personas-password
    optional: true
    items:
      - key: password
        path: zuno_demo__personas__password
- secret:
    # ADR-0320
    name: openshift-client-secret
    optional: true
    items:
      - key: client_secret
        path: zuno_openshift__client__secret
- secret:
    # ADR-0354/WP-072: AAP Gateway's OIDC client, same
    # confidential-client shape as openshift
    # above.
    name: aap-client-secret
    optional: true
    items:
      - key: client_secret
        path: zuno_aap__client__secret
- secret:
    # ADR-0530/WP-091: zuno-admin-api (MaaS externalOIDC
    # client). Note the file name: ${vault.admin_api_client_secret}
    # in realm-zuno.json escapes every underscore of the KEY as
    # "__", so it is zuno_admin__api__client__secret - the realm
    # prefix keeps its single underscore. Getting this wrong
    # fails silently at runtime, per this block's header.
    name: zuno-admin-api-client-secret
    optional: true
    items:
      - key: client_secret
        path: zuno_admin__api__client__secret
- secret:
    # ADR-0535/WP-110: zuno-signer, RHTAS Fulcio's OIDC
    # signing identity. Same underscore-escaping rule as
    # zuno-admin-api above: ${vault.signer_client_secret}
    # resolves to file zuno_signer__client__secret.
    name: zuno-signer-client-secret
    optional: true
    items:
      - key: client_secret
        path: zuno_signer__client__secret
- secret:
    # WP-156: zuno-evaluations, the evaluation harness's
    # persona-token client. ${vault.zuno_evaluations_client_secret}
    # resolves to file zuno_zuno__evaluations__client__secret.
    name: zuno-evaluations-client-secret
    optional: true
    items:
      - key: client_secret
        path: zuno_zuno__evaluations__client__secret
{{- end -}}
