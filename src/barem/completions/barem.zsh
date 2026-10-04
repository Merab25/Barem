#compdef barem

# zsh completion for barem
#
# Install it once, in a directory that is on your $fpath:
#   barem --completion zsh > "${fpath[1]}/_barem"
#   rm -f ~/.zcompdump && compinit
#
# Or load it in the current shell only:
#   source <(barem --completion zsh)

_barem() {
    local -a candidates

    # words[2,CURRENT] is every word after the program name, up to and
    # including the one being typed. `barem --complete` filters the
    # candidates by that last word, so command names, keywords and options
    # all come from the installed example files rather than from a list
    # baked into this script.
    candidates=(${(f)"$(barem --complete "${(@)words[2,CURRENT]}" 2>/dev/null)"})

    # Splitting on newlines leaves a single empty element when there was no
    # output at all; drop it so zsh does not offer an empty match.
    candidates=(${candidates:#})

    (( ${#candidates} )) && compadd -- ${candidates}
}

_barem "$@"
