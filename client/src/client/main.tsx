import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./index.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("缺少 #root。恢复：检查 client.html");
}
createRoot(root).render(<App />);
