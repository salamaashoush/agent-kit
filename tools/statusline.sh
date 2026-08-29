#!/usr/bin/env bash
# Claude Code status line: folder, branch, worktree, model, context, rate, cost.
#
# This runs on every render, so the whole file is bash builtins except one jq
# call and, at most once per CACHE_TTL, one `git status`. The branch and the
# worktree are read out of .git rather than asked of git, which is what keeps a
# typical render at a single fork instead of eight.
#
# Needs jq. The glyphs need a Nerd Font; TERM=linux or CLAUDE_STATUSLINE_ASCII=1
# drops to plain text instead of a row of boxes.

CACHE_TTL=5
BAR_WIDTH=10

# One jq, reading stdin through the process substitution, so no cat either.
# Split on \x1f, not a tab: tab is IFS whitespace, so bash folds a run of them
# into one delimiter and every field after an absent one lands in the wrong
# variable.
IFS=$'\x1f' read -r cwd model used_pct session_id cost duration rate5 rate7 < <(
  jq -r '[(.workspace.current_dir // .cwd // ""),
          (.model.display_name // ""),
          (.context_window.used_percentage // ""),
          (.session_id // ""),
          (.cost.total_cost_usd // ""),
          (.cost.total_duration_ms // ""),
          (.rate_limits.five_hour.used_percentage // ""),
          (.rate_limits.seven_day.used_percentage // "")]
         | map(tostring) | join("\u001f")' 2>/dev/null
)

# ---------------------------------------------------------------------------
# Tokyo Night Storm, in truecolor where the terminal says it can, 256 elsewhere
# ---------------------------------------------------------------------------
if [ "$COLORTERM" = truecolor ] || [ "$COLORTERM" = 24bit ]; then
  C_DIR=$'\e[38;2;122;162;247m'    # #7aa2f7 blue
  C_GIT=$'\e[38;2;187;154;247m'    # #bb9af7 purple
  C_WT=$'\e[38;2;255;158;100m'     # #ff9e64 orange
  C_MODEL=$'\e[38;2;125;207;255m'  # #7dcfff cyan
  C_LABEL=$'\e[38;2;86;95;137m'    # #565f89 comment
  C_LOW=$'\e[38;2;158;206;106m'    # #9ece6a green
  C_MID=$'\e[38;2;224;175;104m'    # #e0af68 yellow
  C_HIGH=$'\e[38;2;247;118;142m'   # #f7768e red
  C_TRACK=$'\e[38;2;65;72;104m'    # #414868 track
else
  C_DIR=$'\e[38;5;110m'
  C_GIT=$'\e[38;5;141m'
  C_WT=$'\e[38;5;215m'
  C_MODEL=$'\e[38;5;117m'
  C_LABEL=$'\e[38;5;243m'
  C_LOW=$'\e[38;5;114m'
  C_MID=$'\e[38;5;222m'
  C_HIGH=$'\e[38;5;203m'
  C_TRACK=$'\e[38;5;237m'
fi
C_RESET=$'\e[0m'
C_BOLD=$'\e[1m'

if [ -n "${CLAUDE_STATUSLINE_ASCII:-}" ] || [ "$TERM" = linux ] || [ "$TERM" = dumb ]; then
  SEP=' | '
  I_DIR='' I_GIT='on ' I_WT='wt ' I_MODEL='' I_CTX='ctx ' I_RATE='rate ' I_TIME=''
  BAR_ON='#' BAR_OFF='-'
else
  SEP=' ' # powerline thin separator
  I_DIR='󰉋 ' I_GIT='󰘬 ' I_WT='󰙅 ' I_MODEL='󱙺 ' I_CTX='󰾆 ' I_RATE='󰓅 ' I_TIME='󰥔 '
  BAR_ON='━' BAR_OFF='━'
fi

# ---------------------------------------------------------------------------
# Folder, with the middle collapsed once the path runs deep
# ---------------------------------------------------------------------------
# Bash 5.2 tilde-expands a replacement, so a literal ~ here would expand back to
# $HOME and shorten nothing. Through a variable it stays a tilde.
tilde='~'
dir="${cwd/#$HOME/$tilde}"
IFS='/' read -ra parts <<< "$dir"
if (( ${#parts[@]} > 4 )); then
  dir="${parts[0]}/${parts[1]}/…/${parts[${#parts[@]}-2]}/${parts[${#parts[@]}-1]}"
fi

# ---------------------------------------------------------------------------
# Branch and worktree, straight out of .git. No fork.
# ---------------------------------------------------------------------------
branch="" worktree="" git_root=""
probe="$cwd"
while [ -n "$probe" ] && [ "$probe" != / ]; do
  if [ -e "$probe/.git" ]; then git_root="$probe"; break; fi
  probe="${probe%/*}"
done

if [ -n "$git_root" ]; then
  if [ -f "$git_root/.git" ]; then
    # A linked worktree or a submodule: "gitdir: /path/.git/worktrees/name"
    read -r _ gitdir < "$git_root/.git" 2>/dev/null
    [ "${gitdir:0:1}" = / ] || gitdir="$git_root/$gitdir"
  else
    gitdir="$git_root/.git"
  fi

  if [ -r "$gitdir/HEAD" ]; then
    read -r head < "$gitdir/HEAD"
    if [ "${head:0:5}" = 'ref: ' ]; then
      branch="${head#ref: refs/heads/}"
    else
      branch="${head:0:7}"
    fi
  fi

  if [[ "$cwd" == */.claude/worktrees/* ]]; then
    rest="${cwd#*/.claude/worktrees/}"
    worktree="${rest%%/*}"
  elif [[ "$gitdir" == */worktrees/* ]]; then
    worktree="${gitdir##*/}"
  fi
fi

# ---------------------------------------------------------------------------
# Working-tree counts. The one command worth caching, keyed per session and dir.
# The timestamp lives in the file so reading it back costs no stat.
# ---------------------------------------------------------------------------
staged=0 modified=0 untracked=0
if [ -n "$git_root" ]; then
  cache_dir="${TMPDIR:-/tmp}/claude-statusline"
  key="${cwd//\//%}"
  (( ${#key} > 180 )) && key="${key:${#key}-180}"
  cache="$cache_dir/${session_id}${key}"
  now=${EPOCHSECONDS:-$(date +%s)}
  fresh=""
  if [ -r "$cache" ]; then
    { read -r stamp; read -r staged modified untracked; } < "$cache" 2>/dev/null
    if [[ "$stamp$staged$modified$untracked" =~ ^[0-9]+$ ]] &&
       (( now - stamp < CACHE_TTL )); then fresh=1; fi
  fi
  if [ -z "$fresh" ]; then
    staged=0 modified=0 untracked=0
    while IFS= read -r entry; do
      if [ "${entry:0:2}" = '??' ]; then
        (( untracked++ ))
      else
        [ "${entry:0:1}" = ' ' ] || (( staged++ ))
        [ "${entry:1:1}" = ' ' ] || (( modified++ ))
      fi
    done < <(git -C "$cwd" status --porcelain --no-renames 2>/dev/null)
    [ -d "$cache_dir" ] || mkdir -p "$cache_dir"
    printf '%s\n%s %s %s\n' "$now" "$staged" "$modified" "$untracked" > "$cache" 2>/dev/null
  fi
fi

# ---------------------------------------------------------------------------
# Assembling the line
# ---------------------------------------------------------------------------
# Sets $hue rather than printing it: a command substitution here would fork,
# which is the whole thing this file is avoiding.
threshold() {
  if   (( $1 < 50 )); then hue="$C_LOW"
  elif (( $1 < 80 )); then hue="$C_MID"
  else                     hue="$C_HIGH"
  fi
}

line=""
join() { [ -n "$line" ] && line+="${C_TRACK}${SEP}${C_RESET}"; line+="$1"; }

[ -n "$dir" ] && join "${C_LABEL}${I_DIR}${C_RESET}${C_DIR}${C_BOLD}${dir}${C_RESET}"

if [ -n "$branch" ]; then
  seg="${C_LABEL}${I_GIT}${C_RESET}${C_GIT}${branch}${C_RESET}"
  (( staged ))    && seg+=" ${C_LOW}+${staged}${C_RESET}"
  (( modified ))  && seg+=" ${C_MID}~${modified}${C_RESET}"
  (( untracked )) && seg+=" ${C_HIGH}?${untracked}${C_RESET}"
  join "$seg"
fi

[ -n "$worktree" ] && join "${C_LABEL}${I_WT}${C_RESET}${C_WT}${worktree}${C_RESET}"
[ -n "$model" ]    && join "${C_LABEL}${I_MODEL}${C_RESET}${C_MODEL}${model}${C_RESET}"

if [ -n "$used_pct" ]; then
  printf -v pct '%.0f' "$used_pct"
  (( pct < 0 )) && pct=0
  (( pct > 100 )) && pct=100
  filled=$(( (pct * BAR_WIDTH + 50) / 100 ))
  threshold "$pct"
  bar=""
  for (( i = 0; i < filled; i++ )); do bar+="$BAR_ON"; done
  track=""
  for (( i = filled; i < BAR_WIDTH; i++ )); do track+="$BAR_OFF"; done
  printf -v pct_txt '%3d%%' "$pct"
  join "${C_LABEL}${I_CTX}${C_RESET}${hue}${bar}${C_TRACK}${track}${C_RESET} ${hue}${C_BOLD}${pct_txt}${C_RESET}"
fi

if [ -n "$rate5" ] || [ -n "$rate7" ]; then
  seg="${C_LABEL}${I_RATE}${C_RESET}"
  if [ -n "$rate5" ]; then
    printf -v r '%.0f' "$rate5"
    threshold "$r"
    seg+="${C_LABEL}5h${C_RESET}${hue}${r}%${C_RESET}"
  fi
  if [ -n "$rate7" ]; then
    printf -v r '%.0f' "$rate7"
    threshold "$r"
    [ -n "$rate5" ] && seg+=" "
    seg+="${C_LABEL}7d${C_RESET}${hue}${r}%${C_RESET}"
  fi
  join "$seg"
fi

if [ -n "$cost" ]; then
  printf -v cost_txt '%.2f' "$cost"
  [ "$cost_txt" != "0.00" ] && join "${C_LABEL}\$${C_RESET}${C_LOW}${cost_txt}${C_RESET}"
fi

if [ -n "$duration" ]; then
  ms=${duration%%.*}
  if (( ms >= 1000 )); then
    s=$(( ms / 1000 )); m=$(( s / 60 )); h=$(( m / 60 ))
    if   (( h )); then span="${h}h $(( m % 60 ))m"
    elif (( m )); then span="${m}m"
    else               span="${s}s"
    fi
    join "${C_LABEL}${I_TIME}${C_RESET}${C_LABEL}${span}${C_RESET}"
  fi
fi

printf '%s\n' "$line"
