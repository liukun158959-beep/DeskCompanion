import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// 不启用 rehype-raw：模型输出里的 HTML 当文本显示，不执行。
// 链接不做成可点击跳转，避免 WebView 把主窗导航走。地址直接写在正文里，可复制。
const components: Components = {
  a({ href, children }) {
    const extra = href && href !== String(children) ? ` ${href}` : "";
    return (
      <span className="md-link">
        {children}
        {extra}
      </span>
    );
  },
};

export function Markdown(props: { text: string }) {
  return (
    <div className="md">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {props.text}
      </ReactMarkdown>
    </div>
  );
}
