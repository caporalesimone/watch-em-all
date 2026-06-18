// Plugin frontend entry (FDISC-R3): exports only the root component. The route
// comes solely from the manifest (route_base); the entry never re-declares it.
import PluginRoot from './PluginRoot.svelte';

export default { component: PluginRoot };
