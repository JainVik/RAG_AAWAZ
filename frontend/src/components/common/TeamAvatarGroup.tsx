import React, { useRef, useState } from 'react';
import {
  Globe,
  GithubLogo,
  LinkedinLogo,
  XLogo,
  ArrowUpRight,
  User,
} from '@phosphor-icons/react';
import { TEAM_MEMBERS, type TeamMember, type SocialType } from '../../config/team';
import { trackDevProfileClicked } from '../../utils/analytics';

interface TeamAvatarGroupProps {
  members?: TeamMember[];
  className?: string;
}

const renderSocialIcon = (type: SocialType) => {
  switch (type) {
    case 'website':
      return <Globe size={13} weight="bold" className="shrink-0 text-cyan-500" />;
    case 'linkedin':
      return <LinkedinLogo size={13} weight="bold" className="shrink-0 text-blue-500" />;
    case 'github':
      return <GithubLogo size={13} weight="bold" className="shrink-0 text-slate-900 dark:text-white" />;
    case 'x':
      return <XLogo size={13} weight="bold" className="shrink-0 text-slate-800 dark:text-slate-200" />;
    default:
      return <ArrowUpRight size={13} weight="bold" className="shrink-0 text-blue-500" />;
  }
};

export const TeamAvatarGroup: React.FC<TeamAvatarGroupProps> = ({
  members = TEAM_MEMBERS,
  className = '',
}) => {
  const [activeId, setActiveId] = useState<string | null>(null);
  const closeTimerRef = useRef<number | null>(null);

  const handleMouseEnter = (id: string) => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
    setActiveId(id);
  };

  const handleMouseLeave = () => {
    closeTimerRef.current = window.setTimeout(() => {
      setActiveId(null);
    }, 250); // 250ms hover grace buffer so user can hover over the card and click links smoothly
  };

  if (!members || members.length === 0) return null;

  return (
    <div
      className={`relative inline-flex items-center group ${className}`}
      aria-label="Developer Profiles"
    >
      {/* Liquid Glass Avatar Capsule */}
      <div className="refractive-glass-pill flex items-center p-1 px-1.5 transition-all duration-300 group-hover:shadow-[0_0_24px_rgba(59,130,246,0.25)]">
        {/* Avatars Stack */}
        <div className="flex items-center -space-x-2.5 group-hover:space-x-1.5 transition-all duration-300 ease-out">
          {members.map((member, index) => {
            const isHovered = activeId === member.id;
            const zIndex = isHovered ? 40 : index + 1;

            return (
              <div
                key={member.id}
                className="relative"
                style={{ zIndex }}
                onMouseEnter={() => handleMouseEnter(member.id)}
                onMouseLeave={handleMouseLeave}
              >
                {/* Avatar Anchor Trigger */}
                <a
                  href={member.profileUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() => {
                    trackDevProfileClicked({
                      dev_name: member.name,
                      link_type: 'portfolio',
                      url: member.profileUrl,
                    });
                  }}
                  aria-label={`${member.name} - View Profile`}
                  className="block relative rounded-full ring-2 ring-white/90 dark:ring-slate-900/90 shadow-sm transition-all duration-200 ease-out transform hover:scale-115 hover:ring-blue-500 hover:shadow-[0_0_14px_rgba(59,130,246,0.6)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:scale-115 cursor-pointer"
                >
                  {member.avatar ? (
                    <img
                      src={member.avatar}
                      alt={member.name}
                      className="w-7 h-7 sm:w-7.5 sm:h-7.5 rounded-full object-cover select-none pointer-events-none bg-slate-200 dark:bg-slate-800"
                      loading="eager"
                    />
                  ) : (
                    <div className="w-7 h-7 sm:w-7.5 sm:h-7.5 rounded-full bg-gradient-to-tr from-blue-600 to-cyan-500 flex items-center justify-center text-[10px] sm:text-[11px] font-bold text-white select-none shadow-inner">
                      {member.initials || <User size={12} weight="bold" />}
                    </div>
                  )}
                  {/* Subtle specular gloss on avatar */}
                  <span
                    className="absolute inset-0 rounded-full pointer-events-none ring-1 ring-inset ring-white/20"
                    aria-hidden="true"
                  />
                </a>

                {/* Floating Tooltip Card - Opens Below, Stays Open On Hover */}
                {isHovered && (
                  <div
                    role="tooltip"
                    onMouseEnter={() => handleMouseEnter(member.id)}
                    onMouseLeave={handleMouseLeave}
                    className="absolute top-full right-0 pt-2 w-52 pointer-events-auto z-50 animate-in fade-in slide-in-from-top-1 duration-150"
                  >
                    <div className="refractive-glass-card p-3 shadow-2xl border border-white/20 dark:border-white/10 rounded-xl backdrop-blur-xl text-left">
                      {/* Developer Name */}
                      <div className="text-xs font-bold text-slate-900 dark:text-white truncate">
                        {member.name}
                      </div>

                      {/* Clickable Social / Profile Links */}
                      <div className="mt-2 space-y-1">
                        {member.links.map((link, idx) => (
                          <a
                            key={idx}
                            href={link.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={() => {
                              trackDevProfileClicked({
                                dev_name: member.name,
                                link_type: link.type,
                                url: link.url,
                              });
                            }}
                            className="flex items-center justify-between px-2.5 py-1.5 rounded-lg text-[11px] font-semibold text-slate-800 dark:text-slate-200 bg-black/5 hover:bg-blue-500/15 hover:text-blue-600 dark:bg-white/5 dark:hover:bg-blue-400/20 dark:hover:text-blue-400 transition-all group/link shadow-xs cursor-pointer"
                          >
                            <div className="flex items-center gap-1.5">
                              {renderSocialIcon(link.type)}
                              <span>{link.label}</span>
                            </div>
                            <ArrowUpRight
                              size={11}
                              weight="bold"
                              className="text-slate-400 dark:text-slate-500 transition-transform group-hover/link:translate-x-0.5 group-hover/link:-translate-y-0.5 group-hover/link:text-blue-500"
                            />
                          </a>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
