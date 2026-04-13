# Patreon Events & Discord Role Assignment

## Tier Roles

Three Discord roles map to Patreon tiers:

| Discord Role | Patreon Tier | Price |
|-------------|-------------|-------|
| `LocoBasic` | LocoBasic | up to $7/mo |
| `LocoStandard` | LocoStandard | up to $15/mo |
| `LocoPremium` | LocoPremium | $16+/mo |

## Role Assignment Logic

The bot assigns roles based on `amount_cents` from the webhook, not the tier name
(Patreon sometimes sends wrong tier names):

```python
def _correct_tier(title, cents):
    if cents <= 700:   return "LocoBasic"
    elif cents <= 1500: return "LocoStandard"
    else:              return "LocoPremium"
```

## Events and Their Role Actions

| Event | Role Action |
|-------|------------|
| `members:pledge:create` | Add correct tier role, remove other tier roles |
| `members:pledge:update` | Add new tier role, remove old tier roles |
| `members:update` (active_patron) | Re-add correct role if missing (after payment) |
| `members:pledge:delete` | Remove **all** tier roles |

## Implementation

```python
_tier_roles = ["LocoBasic", "LocoStandard", "LocoPremium"]
member = guild.get_member(discord_id) or await guild.fetch_member(discord_id)

# Adding a role
roles_to_remove = [r for r in member.roles if r.name in _tier_roles and r.name != tier_title]
await member.remove_roles(*roles_to_remove)
role = discord.utils.get(guild.roles, name=tier_title)
if role and role not in member.roles:
    await member.add_roles(role)

# Removing all roles (cancellation)
roles_to_remove = [r for r in member.roles if r.name in _tier_roles]
await member.remove_roles(*roles_to_remove)
```

## /fix_roles Command

Manual role assignment slash command for the server owner. 
Useful when a member has Patreon but Discord role wasn't assigned (e.g., joined before bot, webhook missed).

Usage: `/fix_roles @user tier:LocoStandard`

## Discord ID Detection

The Discord user ID comes from the webhook's `included` array:
```python
for inc in included:
    if inc["type"] == "user":
        discord_id = inc["attributes"]["social_connections"]["discord"]["user_id"]
```

If the member hasn't connected their Discord to Patreon, `discord_id` is None
and role assignment is skipped silently.

## Known Gap

If a member has Patreon but didn't link their Discord account, no role is assigned.
They need to link Discord in their Patreon settings → triggers a `members:update`
→ bot detects and assigns role.
