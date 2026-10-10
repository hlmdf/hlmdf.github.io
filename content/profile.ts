export type Lang = "zh" | "en";

export type Copy = {
  zh: string;
  en: string;
};

export type PublicationKind = "preprint" | "journal" | "conference";

export type Publication = {
  /** Layout sample. Set this to false once the entry is yours. */
  example: boolean;
  kind: PublicationKind;
  title: Copy;
  authors: string;
  venue: Copy;
  year: string;
  links: { label: Copy; href: string }[];
};

export type Thesis = {
  title: Copy;
  detail: Copy;
  year: Copy;
  links: { label: Copy; href: string }[];
};

export type Talk = {
  example: boolean;
  date: string;
  title: Copy;
  event: Copy;
  place: Copy;
};

export type Education = {
  years: Copy;
  school: Copy;
  detail: Copy;
  crest: string;
};

export type PostImage = {
  /** Sized for the page. */
  src: string;
  /** Opened when the photo is clicked. Defaults to src. */
  full?: string;
};

export type Post = {
  date: Copy;
  title: Copy;
  body?: Copy;
  images?: Array<string | PostImage>;
};

export type Tool = {
  name: Copy;
  href: string;
};

export type ToolGroup = {
  title: Copy;
  items: Tool[];
};

export type SiteLink = {
  name: Copy;
  href: string;
  icon: string;
};

export type SiteGroup = {
  id: string;
  title: Copy;
  items: SiteLink[];
};

/**
 * Everything visitors read lives in this file.
 * Replace the sample rows, then save — the local preview updates on its own.
 */
export const profile = {
  name: {
    zh: "李璇",
    en: "Xuan Li",
  } satisfies Copy,
  siteTitle: {
    zh: "李璇的主页",
    en: "Xuan Li's Homepage",
  } satisfies Copy,
  mark: {
    zh: "李",
    en: "Xuan",
  } satisfies Copy,
  avatar: "/头像.jpg",
  role: {
    zh: "博士生",
    en: "Ph.D. student",
  } satisfies Copy,
  lab: [
    {
      name: {
        zh: "武汉大学人工智能学院",
        en: "School of Artificial Intelligence, Wuhan University",
      },
      href: "https://sai.whu.edu.cn/",
    },
    {
      name: {
        zh: "信息检索与知识挖掘研究所",
        en: "Information Retrieval and Knowledge Mining Laboratory",
      },
      href: "http://39.103.203.133/",
    },
  ],
  place: {
    zh: "武汉大学，湖北省武汉市武昌区",
    en: "Wuhan University, Wuchang, Wuhan, Hubei",
  } satisfies Copy,
  map: "https://www.google.com/maps/search/?api=1&query=Wuhan%20University",
  email: "xuanli7034@163.com",
  wechat: "XuanLi7034",
  github: "https://github.com/hlmdf",
  scholar: "",
  cv: "",
  lookingFor: {
    zh: "欢迎交流学术问题、技术想法，或分享任何有趣的见解。",
    en: "I welcome academic questions, technical ideas, and any interesting observations.",
  } satisfies Copy,
  bio: [
    {
      zh: "你好，欢迎来到我的个人网站！",
      en: "Hello, and welcome to my website.",
    },
    {
      zh: "我目前是武汉大学人工智能学院智能科学与技术专业的博士研究生，拥有计算机科学与技术相关的学术背景。",
      en: "I am a Ph.D. student in Intelligent Science and Technology at the School of Artificial Intelligence, Wuhan University, with an academic background in Computer Science and Technology.",
    },
    {
      zh: "硕士期间，我的研究主要集中在复杂网络与多智能体系统的能控性（Controllability of Complex Networks and Multi-Agent Systems），尤其关注图结构、谱图理论与系统动力学之间的联系，并在 IEEE TNNLS 等学术期刊发表了相关研究成果。",
      en: "During my master's studies, my research focused on the controllability of complex networks and multi-agent systems, especially the connections among graph structure, spectral graph theory, and system dynamics. Related results have appeared in journals including IEEE Transactions on Neural Networks and Learning Systems (TNNLS).",
    },
    {
      zh: "目前，我的研究兴趣正逐步拓展至科技文献多模态理解、知识表示与智能分析等领域。我也希望探索复杂网络、图学习与人工智能方法之间更多有趣的交叉问题。",
      en: "My research interests are now extending toward multimodal understanding of scientific literature, knowledge representation, and intelligent analysis. I also hope to explore further intersections among complex networks, graph learning, and methods in artificial intelligence.",
    },
    {
      zh: "我对人工智能、机器学习、复杂系统以及各种有趣的技术保持着好奇。这个网站主要用于记录我的研究工作、学习笔记、项目实践，以及一些不太成熟但值得保留的想法。",
      en: "I stay curious about artificial intelligence, machine learning, complex systems, and other interesting technologies. This site is mainly a record of my research, study notes, projects, and ideas that are still rough but worth keeping.",
    },
    {
      zh: "保持好奇，持续探索。",
      en: "Stay curious, and keep exploring.",
    },
  ] satisfies Copy[],
  interestsTitle: {
    zh: "正在关注",
    en: "Currently",
  } satisfies Copy,
  interests: [
    {
      zh: "科技文献多模态理解：关注学术文献中文本、图表、公式等多模态信息的理解与表示。",
      en: "Multimodal understanding of scientific literature: how text, figures, and formulas in academic papers are understood and represented.",
    },
    {
      zh: "图学习与复杂网络：探索图神经网络、复杂网络分析与知识建模之间的联系。",
      en: "Graph learning and complex networks: connections among graph neural networks, complex-network analysis, and knowledge modeling.",
    },
    {
      zh: "大语言模型与 AI 工具：学习大语言模型的基本原理、推理部署，以及 OCR、文档解析等技术的实际应用。",
      en: "Large language models and AI tools: the basics of large language models, inference and deployment, and practical uses of OCR and document parsing.",
    },
  ] satisfies Copy[],
  education: [
    {
      years: { zh: "2026–至今", en: "2026–present" },
      crest: "/crests/whu.png",
      school: { zh: "武汉大学", en: "Wuhan University" },
      detail: {
        zh: "人工智能学院，智能科学与技术，博士在读",
        en: "School of Artificial Intelligence, Intelligent Science and Technology, Ph.D. student",
      },
    },
    {
      years: { zh: "2021–2024", en: "2021–2024" },
      crest: "/crests/muc.png",
      school: { zh: "中央民族大学", en: "Minzu University of China" },
      detail: {
        zh: "信息工程学院，计算机科学与技术，硕士",
        en: "School of Information Engineering, Computer Science and Technology, M.S.",
      },
    },
    {
      years: { zh: "2017–2021", en: "2017–2021" },
      crest: "/crests/wust.png",
      school: { zh: "武汉科技大学", en: "Wuhan University of Science and Technology" },
      detail: {
        zh: "计算机科学与技术学院，计算机科学与技术，本科",
        en: "School of Computer Science and Technology, Computer Science and Technology, B.S.",
      },
    },
  ] satisfies Education[],
  publications: [
    {
      example: false,
      kind: "journal",
      title: {
        zh: "Controllability of N-Duplication Corona Product Networks With Laplacian Dynamics",
        en: "Controllability of N-Duplication Corona Product Networks With Laplacian Dynamics",
      },
      authors: "Bo Liu, Xuan Li, Junjie Huang, Housheng Su",
      venue: {
        zh: "IEEE Transactions on Neural Networks and Learning Systems，36 卷 2 期，3693–3707 页",
        en: "IEEE Transactions on Neural Networks and Learning Systems, vol. 36, no. 2, pp. 3693–3707",
      },
      year: "2025",
      links: [
        {
          label: {
            zh: "DOI: 10.1109/TNNLS.2023.3336948",
            en: "DOI: 10.1109/TNNLS.2023.3336948",
          },
          href: "https://doi.org/10.1109/TNNLS.2023.3336948",
        },
        {
          label: { zh: "PDF", en: "PDF" },
          href: "/files/Controllability%20of%20N-Duplication%20Corona%20Product%20Networks%20With%20Laplacian%20Dynamics.pdf",
        },
      ],
    },
    {
      example: false,
      kind: "journal",
      title: {
        zh: "Controllability of neighborhood Corona product networks",
        en: "Controllability of neighborhood Corona product networks",
      },
      authors: "Bo Liu, Xuan Li, Qiang Zhang, Junjie Huang, Housheng Su",
      venue: {
        zh: "中国科学：信息科学，67 卷，文章编号 229202",
        en: "Science China Information Sciences, vol. 67, art. no. 229202",
      },
      year: "2024",
      links: [
        {
          label: {
            zh: "DOI: 10.1007/s11432-023-4179-0",
            en: "DOI: 10.1007/s11432-023-4179-0",
          },
          href: "https://doi.org/10.1007/s11432-023-4179-0",
        },
        {
          label: { zh: "PDF", en: "PDF" },
          href: "/files/Controllability%20of%20neighborhood%20Corona%20product%20networks.pdf",
        },
        {
          label: { zh: "补充材料", en: "Supplementary File" },
          href: "/files/Controllability%20of%20neighborhood%20Corona%20product%20networks%EF%BC%88Supplementary%20File%EF%BC%89.pdf",
        },
      ],
    },
  ] satisfies Publication[],
  theses: [
    {
      title: {
        zh: "Corona图积网络的能控性研究",
        en: "A Study on the Controllability of Corona Graph Product Networks",
      },
      detail: {
        zh: "中央民族大学，硕士，导师刘波",
        en: "Minzu University of China, M.S., advisor Bo Liu",
      },
      year: {
        zh: "2024年5月19日",
        en: "May 19, 2024",
      },
      links: [
        {
          label: { zh: "PDF", en: "PDF" },
          href: "/files/Corona%E5%9B%BE%E7%A7%AF%E7%BD%91%E7%BB%9C%E7%9A%84%E8%83%BD%E6%8E%A7%E6%80%A7%E7%A0%94%E7%A9%B6.pdf",
        },
      ],
    },
  ] satisfies Thesis[],
  talks: [] satisfies Talk[],
  news: [] satisfies Post[],
  life: [
    {
      date: { zh: "2024年", en: "2024" },
      title: {
        zh: "硕士毕业照",
        en: "Master's graduation photos",
      },
      images: [
        {
          src: "/pic/2024/w1600/%E7%A1%95%E5%A3%AB%E6%AF%95%E4%B8%9A%E7%85%A71.jpg",
          full: "/pic/2024/%E7%A1%95%E5%A3%AB%E6%AF%95%E4%B8%9A%E7%85%A71.jpg",
        },
        {
          src: "/pic/2024/w1600/%E7%A1%95%E5%A3%AB%E6%AF%95%E4%B8%9A%E7%85%A72.jpg",
          full: "/pic/2024/%E7%A1%95%E5%A3%AB%E6%AF%95%E4%B8%9A%E7%85%A72.jpg",
        },
        {
          src: "/pic/2024/w1600/%E7%A1%95%E5%A3%AB%E6%AF%95%E4%B8%9A%E7%85%A73.jpg",
          full: "/pic/2024/%E7%A1%95%E5%A3%AB%E6%AF%95%E4%B8%9A%E7%85%A73.jpg",
        },
      ],
    },
    {
      date: { zh: "2021年", en: "2021" },
      title: {
        zh: "本科毕业合照",
        en: "Undergraduate graduation group photo",
      },
      images: [
        "/pic/2021/2021%E6%9C%AC%E7%A7%91%E6%AF%95%E4%B8%9A%E5%90%88%E7%85%A7.jpg",
      ],
    },
  ] satisfies Post[],
  tools: [
    {
      title: { zh: "机场", en: "Proxy services" },
      items: [
        {
          name: { zh: "iKuuu", en: "iKuuu" },
          href: "https://github.com/jdnei/iKuuu",
        },
        {
          name: { zh: "吹雪云", en: "ChuiXueCloud" },
          href: "https://github.com/jdnei/chuixuecloud",
        },
      ],
    },
    {
      title: { zh: "训练、微调框架", en: "Training and fine-tuning frameworks" },
      items: [
        {
          name: { zh: "LlamaFactory", en: "LlamaFactory" },
          href: "https://github.com/hiyouga/LlamaFactory",
        },
      ],
    },
    {
      title: { zh: "浏览器插件", en: "Browser extensions" },
      items: [
        {
          name: { zh: "Microsoft Rewards", en: "Microsoft Rewards" },
          href: "https://github.com/spin311/MicrosoftRewardsWebsite",
        },
      ],
    },
    {
      title: { zh: "学习", en: "Learning" },
      items: [
        {
          name: { zh: "learn-claude-code", en: "learn-claude-code" },
          href: "https://github.com/hlmdf/learn-claude-code",
        },
      ],
    },
  ] satisfies ToolGroup[],
  sites: [
    {
      id: "search",
      title: { zh: "搜索", en: "Search" },
      items: [
        { name: { zh: "Bing", en: "Bing" }, href: "https://www.bing.com", icon: "/icons/links/bing.png" },
        { name: { zh: "Google", en: "Google" }, href: "https://www.google.com", icon: "/icons/links/google.png" },
      ],
    },
    {
      id: "translate",
      title: { zh: "翻译", en: "Translation" },
      items: [
        { name: { zh: "DeepL", en: "DeepL" }, href: "https://www.deepl.com", icon: "/icons/links/deepl.png" },
      ],
    },
    {
      id: "community",
      title: { zh: "社区", en: "Communities" },
      items: [
        { name: { zh: "X", en: "X" }, href: "https://x.com", icon: "/icons/links/x.png" },
        { name: { zh: "TikTok", en: "TikTok" }, href: "https://www.tiktok.com", icon: "/icons/links/tiktok.png" },
        { name: { zh: "抖音", en: "Douyin" }, href: "https://www.douyin.com", icon: "/icons/links/douyin.png" },
        { name: { zh: "哔哩哔哩", en: "Bilibili" }, href: "https://www.bilibili.com", icon: "/icons/links/bilibili.png" },
        { name: { zh: "知乎", en: "Zhihu" }, href: "https://www.zhihu.com", icon: "/icons/links/zhihu.png" },
        { name: { zh: "小红书", en: "Xiaohongshu" }, href: "https://www.xiaohongshu.com", icon: "/icons/links/xiaohongshu.png" },
        { name: { zh: "豆瓣", en: "Douban" }, href: "https://www.douban.com", icon: "/icons/links/douban.png" },
        { name: { zh: "微博", en: "Weibo" }, href: "https://weibo.com", icon: "/icons/links/weibo.png" },
        { name: { zh: "百度贴吧", en: "Baidu Tieba" }, href: "https://tieba.baidu.com", icon: "/icons/links/tieba.png" },
        { name: { zh: "LinkedIn", en: "LinkedIn" }, href: "https://www.linkedin.com", icon: "/icons/links/linkedin.png" },
      ],
    },
    {
      id: "media",
      title: { zh: "影音与游戏", en: "Video and games" },
      items: [
        { name: { zh: "YouTube", en: "YouTube" }, href: "https://www.youtube.com", icon: "/icons/links/youtube.png" },
        { name: { zh: "Steam", en: "Steam" }, href: "https://store.steampowered.com", icon: "/icons/links/steam.png" },
        { name: { zh: "Emu666", en: "Emu666" }, href: "https://www.emu666.com", icon: "/icons/links/emu666.png" },
        { name: { zh: "老男人游戏网", en: "OldmanEmu" }, href: "https://www.oldmanemu.org", icon: "/icons/links/oldmanemu.png" },
        { name: { zh: "Poki", en: "Poki" }, href: "https://poki.com", icon: "/icons/links/poki.png" },
        { name: { zh: "7k7k", en: "7k7k" }, href: "https://www.7k7k.com", icon: "/icons/links/7k7k.png" },
        { name: { zh: "4399", en: "4399" }, href: "https://www.4399.com", icon: "/icons/links/4399.png" },
        { name: { zh: "育碧", en: "Ubisoft" }, href: "https://www.ubisoft.com.cn", icon: "/icons/links/ubisoft.png" },
      ],
    },
    {
      id: "sports",
      title: { zh: "体育", en: "Sports" },
      items: [
        { name: { zh: "腾讯体育", en: "Tencent Sports" }, href: "https://sports.qq.com", icon: "/icons/links/qq-sports.png" },
        { name: { zh: "虎扑", en: "Hupu" }, href: "https://www.hupu.com", icon: "/icons/links/hupu.png" },
        { name: { zh: "企鹅直播", en: "QQ Live" }, href: "https://live.qq.com", icon: "/icons/links/qq-live.png" },
      ],
    },
    {
      id: "wechat",
      title: { zh: "微信", en: "WeChat" },
      items: [
        { name: { zh: "微信读书", en: "WeRead" }, href: "https://weread.qq.com", icon: "/icons/links/weread.png" },
        { name: { zh: "微信网页版", en: "WeChat for Web" }, href: "https://wx.qq.com", icon: "/icons/links/wechat.png" },
      ],
    },
    {
      id: "mail",
      title: { zh: "邮箱", en: "Mail" },
      items: [
        { name: { zh: "QQ邮箱", en: "QQ Mail" }, href: "https://mail.qq.com", icon: "/icons/links/qq-mail.png" },
        { name: { zh: "网易邮箱", en: "NetEase Mail" }, href: "https://mail.163.com", icon: "/icons/links/netease-mail.png" },
        { name: { zh: "Gmail", en: "Gmail" }, href: "https://mail.google.com", icon: "/icons/links/gmail.png" },
        { name: { zh: "Outlook", en: "Outlook" }, href: "https://outlook.live.com", icon: "/icons/links/outlook.png" },
      ],
    },
    {
      id: "everyday",
      title: { zh: "网盘与地图", en: "Cloud and maps" },
      items: [
        { name: { zh: "百度网盘", en: "Baidu Netdisk" }, href: "https://pan.baidu.com", icon: "/icons/links/baidu-pan.png" },
        { name: { zh: "阿里云盘", en: "Aliyun Drive" }, href: "https://www.alipan.com", icon: "/icons/links/alipan.png" },
        { name: { zh: "夸克网盘", en: "Quark Drive" }, href: "https://pan.quark.cn", icon: "/icons/links/quark.png" },
        { name: { zh: "OneDrive", en: "OneDrive" }, href: "https://onedrive.live.com", icon: "/icons/links/onedrive.png" },
        { name: { zh: "百度地图", en: "Baidu Maps" }, href: "https://map.baidu.com", icon: "/icons/links/baidu-map.png" },
        { name: { zh: "高德地图", en: "Amap" }, href: "https://www.amap.com", icon: "/icons/links/amap.png" },
        { name: { zh: "谷歌地图", en: "Google Maps" }, href: "https://maps.google.com", icon: "/icons/links/google-maps.png" },
      ],
    },
    {
      id: "ai",
      title: { zh: "人工智能", en: "AI" },
      items: [
        { name: { zh: "Gemini", en: "Gemini" }, href: "https://gemini.google.com", icon: "/icons/links/gemini.png" },
        { name: { zh: "ChatGPT", en: "ChatGPT" }, href: "https://chatgpt.com", icon: "/icons/links/chatgpt.png" },
        { name: { zh: "DeepSeek", en: "DeepSeek" }, href: "https://chat.deepseek.com", icon: "/icons/links/deepseek.png" },
        { name: { zh: "豆包", en: "Doubao" }, href: "https://www.doubao.com", icon: "/icons/links/doubao.png" },
        { name: { zh: "Claude", en: "Claude" }, href: "https://claude.ai", icon: "/icons/links/claude.png" },
        { name: { zh: "MiniMax", en: "MiniMax" }, href: "https://www.minimax.cn", icon: "/icons/links/minimax.png" },
        { name: { zh: "Kimi", en: "Kimi" }, href: "https://www.kimi.com", icon: "/icons/links/kimi.png" },
        { name: { zh: "GLM", en: "GLM" }, href: "https://chatglm.cn", icon: "/icons/links/glm.png" },
        { name: { zh: "Grok", en: "Grok" }, href: "https://grok.com", icon: "/icons/links/grok.png" },
        { name: { zh: "腾讯混元", en: "Hunyuan" }, href: "https://hunyuan.tencent.com", icon: "/icons/links/hunyuan.png" },
        { name: { zh: "智谱", en: "Zhipu" }, href: "https://www.zhipuai.cn", icon: "/icons/links/zhipu.png" },
        { name: { zh: "Qwen", en: "Qwen" }, href: "https://chat.qwen.ai", icon: "/icons/links/qwen.png" },
        { name: { zh: "MiMo", en: "MiMo" }, href: "https://aistudio.xiaomimimo.com", icon: "/icons/links/mimo.png" },
        { name: { zh: "Muse", en: "Muse" }, href: "https://muse.ai", icon: "/icons/links/muse.png" },
        { name: { zh: "Manus", en: "Manus" }, href: "https://manus.im", icon: "/icons/links/manus.png" },
      ],
    },
    {
      id: "cars",
      title: { zh: "汽车", en: "Cars" },
      items: [
        { name: { zh: "懂车帝", en: "Dongchedi" }, href: "https://www.dongchedi.com", icon: "/icons/links/dongchedi.png" },
        { name: { zh: "汽车之家", en: "Autohome" }, href: "https://www.autohome.com.cn", icon: "/icons/links/autohome.png" },
      ],
    },
    {
      id: "campus",
      title: { zh: "校园", en: "Campus" },
      items: [
        { name: { zh: "智慧珞珈", en: "Smart Luojia" }, href: "https://zhlj.whu.edu.cn", icon: "/icons/links/zhlj.png" },
      ],
    },
  ] satisfies SiteGroup[],
};

export function isPlaceholderEmail(email: string) {
  const value = email.trim().toLowerCase();
  return value.length === 0 || value.endsWith("@example.com");
}

export function isPlaceholderGithub(url: string) {
  const value = url.trim().replace(/\/$/, "");
  return (
    value.length === 0 ||
    value === "https://github.com" ||
    value.includes("your-username")
  );
}
