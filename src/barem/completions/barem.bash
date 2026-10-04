# bash completion for barem
#
# Install it once:
#   mkdir -p ~/.local/share/bash-completion/completions
#   barem --completion bash > ~/.local/share/bash-completion/completions/barem
#
# Or load it in the current shell only:
#   source <(barem --completion bash)

_barem() {
    local candidates

    # Every word after the program name, up to and including the one being
    # typed. `barem --complete` filters the candidates by that last word,
    # so command names, keywords and options all come from the installed
    # example files rather than from a list baked into this script.
    candidates="$(barem --complete "${COMP_WORDS[@]:1:COMP_CWORD}" 2>/dev/null)" || return

    # One candidate per line, and candidates never contain whitespace, so
    # splitting on newlines is what we want here.
    local IFS=$'\n'
    COMPREPLY=($candidates)
}

complete -F _barem barem
