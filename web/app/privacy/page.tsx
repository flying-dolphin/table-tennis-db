import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { APP_NAME, CONTACT_EMAIL, EFFECTIVE_DATE } from "@/lib/constants";

export const metadata = {
  title: `隐私政策 · ${APP_NAME}`,
};

export default function PrivacyPage() {
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
          <h1 className="ml-2 text-body font-semibold text-text-primary">隐私政策</h1>
        </div>
      </div>

      <article className="max-w-2xl mx-auto px-5 py-8 pb-24">
        <p className="text-caption text-text-tertiary mb-6">生效日期：{EFFECTIVE_DATE}</p>

        <p className="text-body text-text-secondary leading-relaxed mb-8">
          {APP_NAME}（以下简称"我们"）非常重视您的隐私保护。本政策说明我们如何收集、使用和保护您在使用本平台过程中产生的信息。请在使用前仔细阅读。
        </p>

        <Section title="一、我们收集哪些信息">
          <SubSection label="您主动提供的信息">
            <ul>
              <li><strong>邮箱地址</strong>：注册账号时必填，用于唯一标识您的账号。</li>
              <li><strong>用户名</strong>：注册时自行设定的昵称，会在平台内公开显示。</li>
              <li><strong>密码</strong>：经过加密哈希处理后存储，我们无法获取您的明文密码。</li>
            </ul>
          </SubSection>
          <SubSection label="自动产生的信息">
            <ul>
              <li><strong>会话 Cookie</strong>：登录后我们会在您的浏览器中设置一个 HttpOnly 会话 Cookie，用于维持登录状态，有效期 30 天。</li>
              <li><strong>搜索记录</strong>：您通过智能搜索功能提交的查询内容，用于返回搜索结果。目前我们不对搜索记录进行持久化存储。</li>
            </ul>
          </SubSection>
          <SubSection label="我们不收集的信息">
            <ul>
              <li>我们不收集您的真实姓名、手机号码、身份证号或支付信息。</li>
              <li>我们不追踪您的地理位置。</li>
              <li>我们不使用第三方广告追踪工具。</li>
            </ul>
          </SubSection>
        </Section>

        <Section title="二、信息使用方式">
          <p>我们仅将您的信息用于以下目的：</p>
          <ul>
            <li><strong>账号认证</strong>：验证您的登录状态，确保只有您本人可访问账号。</li>
            <li><strong>功能提供</strong>：登录状态是使用智能搜索等核心功能的前提条件。</li>
            <li><strong>安全保护</strong>：检测并阻止异常登录、滥用行为及暴力破解攻击。</li>
            <li><strong>服务改进</strong>：了解功能使用情况，以持续优化产品体验。</li>
          </ul>
          <p>我们不会将您的个人信息用于商业营销目的。</p>
        </Section>

        <Section title="三、信息存储与安全">
          <ul>
            <li>您的账号数据存储在本平台服务器的 SQLite 数据库中。</li>
            <li>密码使用 <code className="text-caption bg-surface-tinted px-1 rounded">scrypt</code> 算法加密哈希后存储，即使数据库泄露也无法还原明文密码。</li>
            <li>会话令牌使用加密随机数生成，每次登录产生唯一 token。</li>
            <li>我们采取合理的技术措施保护数据安全，但无法保证 100% 安全。如发生数据安全事件，我们将尽快通知受影响用户。</li>
          </ul>
        </Section>

        <Section title="四、Cookie 说明">
          <p>
            本平台仅使用一个名为 <code className="text-caption bg-surface-tinted px-1 rounded">ittf_session</code> 的 HttpOnly Cookie，用于保持您的登录状态。该 Cookie：
          </p>
          <ul>
            <li>仅在您登录后设置，有效期 30 天；</li>
            <li>设置了 HttpOnly 属性，JavaScript 无法读取，有效防止 XSS 攻击；</li>
            <li>设置了 SameSite=Lax 属性，防止跨站请求伪造；</li>
            <li>退出登录后立即失效并被清除。</li>
          </ul>
          <p>我们不使用广告 Cookie 或第三方追踪 Cookie。</p>
        </Section>

        <Section title="五、信息共享">
          <p>
            我们不会向任何第三方出售、出租或交换您的个人信息。以下情况除外：
          </p>
          <ul>
            <li><strong>法律要求</strong>：在法律法规要求或政府机关依法要求时，我们可能依法提供必要信息。</li>
            <li><strong>安全保护</strong>：为防止欺诈或保护用户安全时的必要行为。</li>
          </ul>
        </Section>

        <Section title="六、您的权利">
          <p>您对自己的个人信息拥有以下权利：</p>
          <ul>
            <li><strong>查看</strong>：登录后可在"我的"页面查看您的账号信息。</li>
            <li><strong>注销</strong>：您可随时联系我们申请注销账号，注销后我们将删除您的账号信息。</li>
            <li><strong>退出登录</strong>：可随时在"我的"页面退出登录，清除会话状态。</li>
          </ul>
          <p>如需行使上述权利，请发送邮件至 <a href={`mailto:${CONTACT_EMAIL}`} className="text-brand-deep hover:underline">{CONTACT_EMAIL}</a>。</p>
        </Section>

        <Section title="七、未成年人保护">
          <p>
            本平台不针对 14 周岁以下未成年人。若您是未成年人，请在监护人陪同下阅读本政策并在监护人同意后使用本平台。
          </p>
        </Section>

        <Section title="八、隐私政策更新">
          <p>
            我们可能不定期更新本隐私政策。政策发生重大变更时，我们将在平台内发布通知。继续使用本平台即视为您同意更新后的政策。
          </p>
        </Section>

        <Section title="九、联系我们">
          <p>
            如您对本隐私政策有任何疑问或投诉，请通过以下方式联系我们：
          </p>
          <p>
            邮箱：<a href={`mailto:${CONTACT_EMAIL}`} className="text-brand-deep hover:underline">{CONTACT_EMAIL}</a>
          </p>
          <p className="text-caption text-text-tertiary mt-4">
            我们将在收到邮件后 7 个工作日内回复。
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

function SubSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-body font-medium text-text-primary mb-2">{label}</h3>
      {children}
    </div>
  );
}
