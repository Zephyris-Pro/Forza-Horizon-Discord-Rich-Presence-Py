Based on 1Stalk's [Forza Horizon Discord Rich Presence](https://github.com/1Stalk/Forza-Horizon-Discord-Rich-Presence), this is a Python port with additional improvements.

In-game status is retrieved directly from Microsoft's servers, no [OpenXBL](https://xbl.io) dependency. The XAuth token is extracted by reading Xbox process memory, which is then used to authenticate against Microsoft's API.
