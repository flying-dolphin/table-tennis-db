import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { APP_NAME, CONTACT_EMAIL, EFFECTIVE_DATE } from "@/lib/constants";

export const metadata = {
  title: `用户协议 · ${APP_NAME}`,
};

export default function TermsPage() {
  return (
    <main className="min-h-screen bg-white">
      <div className="sticky top-0 z-10 bg-white/90 backdrop-blur-sm border-b border-border-subtle">
        <div className="flex items-center gap-2 px-4 h-14 max-w-2xl mx-auto">
          <Link
            href="/"
            className="flex items-center gap-1 text-text-secondary hover:text-text-primary transition-colors"
          >
            <ChevronLeft size={20} />
            <span className="text-body">返回</span>
          </Link>
          <h1 className="ml-2 text-body font-semibold text-text-primary">用户协议</h1>
        </div>
      </div>

      <article className="max-w-2xl mx-auto px-5 py-8 pb-24 prose-custom">
        <p className="text-caption text-text-tertiary mb-6">生效日期：{EFFECTIVE_DATE}</p>

        <p className="text-body text-text-secondary leading-relaxed mb-8">
          欢迎使用{APP_NAME}（以下简称"本平台"或"我们"）。在使用本平台前，请仔细阅读并理解以下用户协议。注册或使用本平台即表示您已阅读、理解并同意受本协议约束。
        </p>

        <Section title="一、服务说明">
          <p>
            {APP_NAME}是一个专注于展示 ITTF（国际乒联）女子乒乓球赛事数据的信息查询平台，提供球员排名、赛事成绩、历史对阵记录及智能搜索等功能。本平台数据来源于 ITTF 官方公开资料，仅供参考与学习交流使用。
          </p>
        </Section>

        <Section title="二、账号注册与使用">
          <ul>
            <li>您需要注册账号方可使用智能搜索等核心功能。</li>
            <li>注册时须提供真实有效的邮箱地址，并设置符合规范的用户名与密码。</li>
            <li>您有责任妥善保管账号密码，因密码泄露导致的损失由您自行承担。</li>
            <li>用户名要求：3-20 个字符，由字母、数字和下划线组成，且须以字母或数字开头。</li>
            <li>每个邮箱仅可注册一个账号。</li>
            <li>您不得将账号转让、出租或授权他人使用。</li>
          </ul>
        </Section>

        <Section title="三、用户行为规范">
          <p>使用本平台时，您承诺不进行以下行为：</p>
          <ul>
            <li>以自动化方式（爬虫、脚本等）大量抓取平台数据；</li>
            <li>对平台进行任何形式的攻击、干扰或破坏；</li>
            <li>传播虚假信息或误导性内容；</li>
            <li>利用本平台从事任何违反中国大陆或您所在地区法律法规的活动；</li>
            <li>滥用智能搜索功能，包括但不限于频繁发起恶意请求；</li>
            <li>尝试绕过本平台的访问控制或安全机制。</li>
          </ul>
        </Section>

        <Section title="四、数据来源与版权声明">
          <p>
            本平台展示的赛事成绩、球员信息、排名数据均整理自 ITTF（国际乒联）官方网站等公开渠道，版权归原始数据来源方所有。本平台对数据进行了结构化整理，但不对数据的实时性、准确性或完整性作出任何保证。
          </p>
          <p>
            本平台的界面设计、代码及原创内容版权归开发者所有，未经授权不得复制或商业使用。
          </p>
        </Section>

        <Section title="五、免责声明">
          <ul>
            <li>本平台数据仅供参考，不构成任何形式的专业建议。</li>
            <li>本平台不对数据的实时准确性负责，官方最新数据请以 ITTF 官方渠道为准。</li>
            <li>本平台保留随时修改、暂停或终止服务的权利，无需事先通知。</li>
            <li>因不可抗力或第三方原因导致的服务中断，本平台不承担责任。</li>
          </ul>
        </Section>

        <Section title="六、服务变更与终止">
          <p>
            我们保留随时修改本协议、调整功能或终止服务的权利。协议变更后将在平台内通知，继续使用即视为同意新协议。若您不同意变更，可停止使用并注销账号。
          </p>
        </Section>

        <Section title="七、适用法律">
          <p>
            本协议的签订、解释及纠纷解决均适用中华人民共和国法律。如发生争议，双方应友好协商解决。
          </p>
        </Section>

        <Section title="八、联系我们">
          <p>
            如您对本协议有任何疑问，欢迎通过邮箱联系：
            <a href={`mailto:${CONTACT_EMAIL}`} className="text-brand-deep hover:underline ml-1">
              {CONTACT_EMAIL}
            </a>
          </p>
        </Section>
      </article>
    </main>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-8">
      <h2 className="text-heading-2 font-semibold text-text-primary mb-3">{title}</h2>
      <div className="text-body text-text-secondary leading-relaxed space-y-3">
        {children}
      </div>
    </section>
  );
}
