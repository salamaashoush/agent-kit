#!/usr/bin/env bash
# Claude Code status line: folder, branch, worktree, model, context, tokens,
# rate, cost.
#
# This runs on every render, so the whole file is bash builtins except one jq
# call, one awk over the new lines of the transcript, and, at most once per
# CACHE_TTL, one `git status`. The branch and the worktree are read out of .git
# rather than asked of git, which is what keeps a typical render at two forks
# instead of eight.
#
# Needs jq. The glyphs need a Nerd Font; TERM=linux or CLAUDE_STATUSLINE_ASCII=1
# drops to plain text instead of a row of boxes.

CACHE_TTL=5
BAR_WIDTH=10

# One jq, reading stdin through the process substitution, so no cat either.
# Split on \x1f, not a tab: tab is IFS whitespace, so bash folds a run of them
# into one delimiter and every field after an absent one lands in the wrong
# variable.
IFS=$'\x1f' read -r cwd model model_id fast used_pct session_id cost duration rate5 rate7 transcript < <(
  jq -r '[(.workspace.current_dir // .cwd // ""),
          (.model.display_name // ""),
          (.model.id // ""),
          (.fast_mode // ""),
          (.context_window.used_percentage // ""),
          (.session_id // ""),
          (.cost.total_cost_usd // ""),
          (.cost.total_duration_ms // ""),
          (.rate_limits.five_hour.used_percentage // ""),
          (.rate_limits.seven_day.used_percentage // ""),
          (.transcript_path // "")]
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
  C_FG=$'\e[38;2;192;202;245m'    # #c0caf5 foreground
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
  C_FG=$'\e[38;5;189m'
fi
C_RESET=$'\e[0m'
C_BOLD=$'\e[1m'

if [ -n "${CLAUDE_STATUSLINE_ASCII:-}" ] || [ "$TERM" = linux ] || [ "$TERM" = dumb ]; then
  SEP=' | '
  I_DIR='' I_GIT='on ' I_WT='wt ' I_MODEL='' I_CTX='ctx ' I_TOK='tok ' I_RATE='rate ' I_TIME=''
  BAR_ON='#' BAR_OFF='-'
  DOT='  '
else
  SEP=' ' # powerline thin separator
  I_DIR='󰉋 ' I_GIT='󰘬 ' I_WT='󰙅 ' I_MODEL='󱙺 ' I_CTX='󰾆 ' I_TOK='󰆼 ' I_RATE='󰓅 ' I_TIME='󰥔 '
  BAR_ON='━' BAR_OFF='━'
  DOT=' · '
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
cache_dir="${TMPDIR:-/tmp}/claude-statusline"

staged=0 modified=0 untracked=0
if [ -n "$git_root" ]; then
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
# Tokens billed to this session, subagents included
# ---------------------------------------------------------------------------
# The payload stops at dollars, so the transcript is the only place the count
# lives. A subagent turn is written into the session's own transcript with
# isSidechain set, which is what makes one pass cover both. Two traps: an
# assistant entry repeats its whole usage object once per content block, always
# on adjacent lines, so the message id carries across renders to stop a split
# message counting twice; and a tool input can contain the literal text of a
# usage field, so the numbers are read from the last "usage":{ on the line
# rather than the first match anywhere in it.
tok_total=0 tok_sub=0
if [ -z "$transcript" ] && [ -n "$session_id" ] && [ -n "$cwd" ]; then
  slug="${cwd//\//-}"
  transcript="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects/${slug//./-}/${session_id}.jsonl"
fi

if [ -r "$transcript" ]; then
  tcache="$cache_dir/${session_id}.tok"
  tok_lines=0 tok_id=""
  if [ -r "$tcache" ]; then
    { read -r tok_lines tok_total tok_sub; read -r tok_id; } < "$tcache" 2>/dev/null
    [[ "$tok_lines$tok_total$tok_sub" =~ ^[0-9]+$ ]] ||
      { tok_lines=0 tok_total=0 tok_sub=0 tok_id=""; }
  fi

  read -r nr d_total d_sub d_id < <(
    LC_ALL=C awk -v start="$tok_lines" -v prev="$tok_id" '
      function num(s, key,   n) {
        n = length(key)
        return match(s, key "[0-9]+") ? substr(s, RSTART + n, RLENGTH - n) + 0 : 0
      }
      NR <= start { next }
      index($0, "\"type\":\"assistant\"") == 0 { next }
      {
        n = split($0, u, "\"usage\":{")
        if (n < 2) next
        id = ""
        if (match($0, /"id":"msg_[^"]*"/)) id = substr($0, RSTART + 6, RLENGTH - 7)
        if (id != "" && id == prev) next
        prev = id
        t = num(u[n], "\"input_tokens\":") + num(u[n], "\"output_tokens\":") \
          + num(u[n], "\"cache_read_input_tokens\":") \
          + num(u[n], "\"cache_creation_input_tokens\":")
        total += t
        if (index($0, "\"isSidechain\":true")) side += t
      }
      END { print NR, total + 0, side + 0, prev }
    ' "$transcript" 2>/dev/null
  )

  if [[ "$nr$d_total$d_sub" =~ ^[0-9]+$ ]]; then
    if (( nr < tok_lines )); then
      # The file lost lines, so the running total describes a file that is gone.
      tok_lines=0 tok_total=0 tok_sub=0 tok_id=""
    else
      tok_lines=$nr
      (( tok_total += d_total, tok_sub += d_sub, 1 ))
      [ -n "$d_id" ] && tok_id="$d_id"
    fi
    [ -d "$cache_dir" ] || mkdir -p "$cache_dir"
    printf '%s %s %s\n%s\n' "$tok_lines" "$tok_total" "$tok_sub" "$tok_id" \
      > "$tcache" 2>/dev/null
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

# Sets $num, for the same reason threshold() sets $hue.
humanize() {
  if   (( $1 >= 1000000 )); then num="$(( $1 / 1000000 )).$(( ($1 % 1000000) / 100000 ))M"
  elif (( $1 >= 1000 ));    then num="$(( $1 / 1000 ))K"
  else                           num="$1"
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

if [ -n "$worktree" ] && [ "$worktree" != "$branch" ] && [[ "$dir" != *"$worktree"* ]]; then
  join "${C_LABEL}${I_WT}${C_RESET}${C_WT}${worktree}${C_RESET}"
fi
[ -n "$model" ] && join "${C_LABEL}${I_MODEL}${C_RESET}${C_MODEL}${model}${C_RESET}"

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

if (( tok_total )); then
  humanize "$tok_total"
  seg="${C_LABEL}${I_TOK}${C_RESET}${C_FG}${C_BOLD}${num}${C_RESET}"
  if (( tok_sub )); then
    humanize "$tok_sub"
    seg+="${C_TRACK}${DOT}${C_RESET}${C_LABEL}sub ${C_RESET}${C_FG}${num}${C_RESET}"
  fi
  join "$seg"
fi

if [ -n "$rate5" ] || [ -n "$rate7" ]; then
  seg="${C_LABEL}${I_RATE}${C_RESET}"
  if [ -n "$rate5" ]; then
    printf -v r '%.0f' "$rate5"
    threshold "$r"
    seg+="${C_LABEL}5h ${C_RESET}${hue}${r}%${C_RESET}"
  fi
  if [ -n "$rate7" ]; then
    printf -v r '%.0f' "$rate7"
    threshold "$r"
    [ -n "$rate5" ] && seg+="${C_TRACK}${DOT}${C_RESET}"
    seg+="${C_LABEL}7d ${C_RESET}${hue}${r}%${C_RESET}"
  fi
  join "$seg"
fi

# Cost, then what a million tokens actually came to. The two are worth seeing
# together because a cache read bills at a tenth of the input rate and a cache
# write at twice it, so the blended rate is the only thing on the line that says
# whether the cache is working: it sits near a fifth of list while the prefix
# holds, and climbs towards list when something invalidates it every turn. Which
# is why the list rate is still read here after it stopped being printed, in
# cents per million so the bands scale to the model rather than to Opus.
list_in=0 price_key="${model_id:-$model}"
case "${price_key%%\[*}" in
  *[Ff]able?5*|*[Mm]ythos?5*)  list_in=1000 ;;
  *[Oo]pus?5*|*[Oo]pus?4?8*)   list_in=500; [ "$fast" = true ] && list_in=1000 ;;
  *[Oo]pus?4?7*|*[Oo]pus?4?6*) list_in=500 ;;
  *[Ss]onnet?5*)               list_in=200 ;;
  *[Ss]onnet?4?6*)             list_in=300 ;;
  *[Hh]aiku?4?5*)              list_in=100 ;;
esac

if [ -n "$cost" ]; then
  printf -v cost_txt '%.2f' "$cost"
  if [ "$cost_txt" != "0.00" ]; then
    seg="${C_LABEL}\$${C_RESET}${C_FG}${cost_txt}${C_RESET}"
    if (( tok_total )); then
      # printf reads the exponent, which is the only way to a float here.
      printf -v cents '%.0f' "${cost_txt}e2"
      blended=$(( cents * 1000000 / tok_total ))
      if   (( list_in == 0 ));               then hue="$C_LABEL"
      elif (( blended * 3 < list_in ));      then hue="$C_LOW"
      elif (( blended * 3 < list_in * 2 ));  then hue="$C_MID"
      else                                        hue="$C_HIGH"
      fi
      printf -v rate_txt '$%d.%02d/M' $(( blended / 100 )) $(( blended % 100 ))
      seg+="${C_TRACK}${DOT}${C_RESET}${hue}${rate_txt}${C_RESET}"
    fi
    join "$seg"
  fi
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
