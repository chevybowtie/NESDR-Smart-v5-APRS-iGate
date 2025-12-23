# if a neo-rx venv is active, deactivate it
deactivate 2>/dev/null || true

# remove install tree (replace path if you used a custom --target-dir)
rm -rf ~/.local/share/neo-rx/.venv
rm -rf ~/.local/share/neo-rx/extracted
rm -rf ~/.local/share/neo-rx/logs
rm -rf ~/.local/share/neo-rx/instances

# Ask before removing user config
if [ -d "$HOME/.config/neo-rx" ]; then
	printf "Remove user config at %s? [y/N]: " "$HOME/.config/neo-rx"
	IFS= read -r _ans || true
	case "$_ans" in
		[Yy]*)
			rm -rf "$HOME/.config/neo-rx"
			echo "Removed $HOME/.config/neo-rx"
			;;
		*)
			echo "Skipping removal of $HOME/.config/neo-rx"
			;;
	esac
else
	echo "No user config found at $HOME/.config/neo-rx"
fi