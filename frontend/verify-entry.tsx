// Verification-only entry: mounts the SAME production App component so jsdom
// (which cannot execute <script type="module">) can drive the real UI.
// The production image still uses the normal Vite build from src/main.tsx;
// run.sh generates this bundle with esbuild alongside the vite build.
import { createRoot } from "react-dom/client";
import App from "./src/App";

createRoot(document.getElementById("root")!).render(<App />);
