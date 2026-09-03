import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("petAPI", {
  ignoreMouse(ignore) {
    ipcRenderer.send("ignore-mouse", ignore);
  },
  modelReady() {
    ipcRenderer.send("model-ready");
  },
  modelFailed(message) {
    ipcRenderer.send("model-failed", message);
  },
  dragBy(dx, dy) {
    ipcRenderer.send("drag-by", dx, dy);
  },
  dragEnd() {
    ipcRenderer.send("drag-end");
  },
  contextMenu() {
    ipcRenderer.send("context-menu");
  },
  openBoard() {
    ipcRenderer.send("open-board");
  },
  setBubble(open) {
    return ipcRenderer.invoke("set-bubble", open);
  },
  toggleChat() {
    ipcRenderer.send("toggle-chat");
  },
  call(method, params) {
    return ipcRenderer.invoke("call", method, params);
  },
  persistScale(scale) {
    ipcRenderer.send("set-scale", scale);
  },
  onSetLayout(handler) {
    ipcRenderer.on("set-layout", (_e, layout) => handler(layout));
  },
  onBridge(handler) {
    ipcRenderer.on("bridge-event", (_e, msg) => handler(msg));
  },
  onPlayMotion(handler) {
    ipcRenderer.on("play-motion", (_e, group) => handler(group));
  },
  onSetScale(handler) {
    ipcRenderer.on("set-scale", (_e, scale) => handler(scale));
  },
});
