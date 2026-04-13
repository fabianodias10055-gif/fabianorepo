# Discord Role System

## Tier Roles

| Role Name | Who Gets It |
|-----------|------------|
| `LocoBasic` | Patreon members paying up to $7/mo |
| `LocoStandard` | Patreon members paying up to $15/mo |
| `LocoPremium` | Patreon members paying $16+/mo |
| `Member` | Anyone who joins the Discord server |

## Automatic Assignment

Roles are assigned automatically when Patreon webhooks arrive.
See [[Events & Roles]] for the full logic.

Trigger events:
- `members:pledge:create` → assign tier role
- `members:pledge:update` → swap to new tier role
- `members:update` with `patron_status=active_patron` → re-assign if missing
- `members:pledge:delete` → remove all tier roles

## /fix_roles Command

Manual role fix command for server owner. Used when:
- A member subscribed before the bot was running
- Webhook was missed
- Member linked Discord to Patreon after subscribing

```
/fix_roles user:@username tier:LocoStandard
```

Internally calls `update_link()` and then does the same role-assignment logic
as the webhook handler.

## Member Role on Join

When someone joins the Discord server (`on_member_join`), they get:
- The `Member` role
- A welcome DM

This is separate from Patreon tier roles.

## Role Hierarchy Notes

- A member can only have **one** tier role at a time
- When upgrading (e.g., Basic → Standard), old role is removed first
- Bot needs the "Manage Roles" permission in Discord
- Bot's role must be **higher** than the roles it manages in the role list
