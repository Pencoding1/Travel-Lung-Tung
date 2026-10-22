# Model identity correction — 2026-10-17

The user explicitly clarifies that `ds/deepseek-flash` is **DeepSeek V4.1 Flash** and instructs us **not to use an explicitly named V4.0 Flash model**. The existing provider-qualified route is `aibox/ds/deepseek-flash`; retain that exact working route. Do not replace it with a guessed 4.1 identifier or any V4.0 route.

Use DeepSeek V4.1 Flash as the user-confirmed identity in current prose/UI metadata. Preserve raw historical exports/configured display strings as evidence, even when they say V4 Flash. Distinguish user confirmation from independent upstream verification; do not fabricate a provider attestation or silently rewrite historical run evidence. Earlier handoff claims that user identity is unresolved are superseded by this clarification.

Next session: enforce this model constraint throughout remaining implementation and experiments. Complete all remaining MASTER_GOAL tasks; checkpoint after each major phase. OC038R1 process80001 and OC041 process57252 were still live on this check. OC040's old process handle97717 is no longer available and its log ends in stop/final text; its report remains subject to independent acceptance.
