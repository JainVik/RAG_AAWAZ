import susImg from '../assets/team/sus.png';
import vikarshImg from '../assets/team/vikarsh.jpeg';
import shubhamImg from '../assets/team/shubham.jpeg';

export type SocialType = 'website' | 'linkedin' | 'github' | 'x';

export interface ProfileLink {
  label: string;
  url: string;
  type: SocialType;
}

export interface TeamMember {
  id: string;
  name: string;
  initials: string;
  avatar: string;
  profileUrl: string;
  links: ProfileLink[];
}

export const TEAM_MEMBERS: TeamMember[] = [
  {
    id: 'dev-1',
    name: 'Shashank Jain',
    initials: 'SJ',
    avatar: susImg,
    profileUrl: 'https://susdev.in/',
    links: [
      { label: 'Portfolio', url: 'https://susdev.in/', type: 'website' },
      { label: 'LinkedIn', url: 'https://www.linkedin.com/in/shashank-jain-6b7955173/', type: 'linkedin' },
      { label: 'GitHub', url: 'https://github.com/sus-qodes', type: 'github' },
      { label: 'X', url: 'https://x.com/susqodes', type: 'x' },
    ],
  },
  {
    id: 'dev-2',
    name: 'Vikarsh Jain',
    initials: 'VJ',
    avatar: vikarshImg,
    profileUrl: 'https://www.linkedin.com/in/vikarshjain/',
    links: [
      { label: 'LinkedIn', url: 'https://www.linkedin.com/in/vikarshjain/', type: 'linkedin' },
      { label: 'GitHub', url: 'https://github.com/JainVik', type: 'github' },
      { label: 'X', url: 'https://x.com/jainvik8989', type: 'x' },
    ],
  },
  {
    id: 'dev-3',
    name: 'Shubham Das',
    initials: 'SD',
    avatar: shubhamImg,
    profileUrl: 'https://shubhamdas27.vercel.app/',
    links: [
      { label: 'Portfolio', url: 'https://shubhamdas27.vercel.app/', type: 'website' },
      { label: 'LinkedIn', url: 'https://www.linkedin.com/in/shubhamdas27/', type: 'linkedin' },
      { label: 'GitHub', url: 'https://github.com/Shubhamdas27', type: 'github' },
      { label: 'X', url: 'https://x.com/Shubham90259252', type: 'x' },
    ],
  },
];
