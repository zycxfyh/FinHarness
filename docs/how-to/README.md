# How-to Guides

How-to guides are task recipes for users who already understand the golden path.
They should answer "how do I do this one job?" without explaining the whole
architecture.

Start with the tutorial first: [Golden Path Tutorial](../tutorials/golden-path.md).

## Available Now

- First safe end-to-end run: [Golden Path Tutorial](../tutorials/golden-path.md).
- Command lookup while recipes are being expanded: [Command Reference](../reference/commands.md).
- Layer-specific responsibilities: [Module Docs](../modules/README.md).

| How-to | Use it when | Current entry point |
| --- | --- | --- |
| [Do a safe paper-trade review](safe-paper-trade-review.md) | You need broker workflow evidence without live authority. | `task alpaca:paper-strategy-order` |
| [Add a mature-wheel adapter](add-mature-wheel-adapter.md) | You are replacing local heavy logic with a mature library. | [Mature Wheel Control Plane](../architecture/mature-wheel-control-plane.md) |
| [Import a personal-finance export](import-personal-finance-export.md) | You have a Beancount ledger or a FinHarness-contract CSV to mirror into state core. | `task beancount:import` / `task personal-finance:import` |
| [Promote a lesson draft into a rule change](promote-lesson-to-rule.md) | A human has reviewed a lesson and wants traceable rule lineage. | `task lessons:promote`, `task rules:audit` |

Safety rule for every how-to: teach the brake in the same document as the
action. No recipe should make trading feel like a one-click path.
