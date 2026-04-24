import nodemailer from 'nodemailer';
import { APP_NAME } from "@/lib/constants";


const transporter = nodemailer.createTransport({
  host: process.env.SMTP_HOST ?? 'smtp.gmail.com',
  port: Number(process.env.SMTP_PORT ?? 465),
  secure: (process.env.SMTP_SECURE ?? 'true') !== 'false',
  auth: {
    user: process.env.SMTP_USER ?? '',
    pass: process.env.SMTP_PASS ?? '',
  },
});

const FROM = process.env.SMTP_FROM ?? process.env.SMTP_USER ?? 'noreply@example.com';
const APP_NAME_MAIL = process.env.NEXT_PUBLIC_APP_NAME ?? APP_NAME;

export async function sendVerificationCode(to: string, code: string): Promise<void> {
  await transporter.sendMail({
    from: `"${APP_NAME_MAIL}" <${FROM}>`,
    to,
    subject: `${code} 是你的验证码`,
    text: `你的验证码是：${code}\n\n有效期 10 分钟，请勿泄露给他人。`,
    html: `
      <div style="font-family:sans-serif;max-width:480px;margin:auto">
        <h2 style="color:#3B82F6">${APP_NAME_MAIL}</h2>
        <p>你的邮箱验证码为：</p>
        <p style="font-size:36px;font-weight:bold;letter-spacing:8px;color:#1e293b">${code}</p>
        <p style="color:#64748b;font-size:14px">有效期 10 分钟，请勿泄露给他人。</p>
      </div>
    `,
  });
}
