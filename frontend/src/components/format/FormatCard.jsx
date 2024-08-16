import PropTypes from 'prop-types';

function FormatCard({ format, onEdit, onClone, showDate, formatDate }) {
  return (
    <div
      className="bg-white dark:bg-gray-800 shadow-lg hover:shadow-xl rounded-lg p-4 cursor-pointer border border-gray-200 dark:border-gray-700 transition-all duration-300 ease-in-out transform hover:-translate-y-1"
      onClick={() => onEdit(format)}
    >
      <div className="flex justify-between items-center">
        <h3 className="font-bold text-lg text-gray-800 dark:text-gray-200">
          {format.name}
        </h3>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onClone(format);
          }}
          className="text-blue-500 hover:text-blue-700"
        >
          <img src="/clone.svg" alt="Clone" className="w-6 h-6" />
        </button>
      </div>
      <p className="text-gray-600 dark:text-gray-400 text-sm mb-2">{format.description}</p>
      {showDate && (
        <p className="text-gray-500 dark:text-gray-400 text-xs mb-2">
          Modified: {formatDate(format.date_modified)}
        </p>
      )}
      <div className="flex flex-wrap -m-1 mt-4">
        {format.conditions.map((condition, index) => (
          <span
            key={index}
            className={`text-xs font-medium inline-block py-1 px-2 rounded m-1 ${
              condition.negate ? 'bg-red-500 text-white' :
              condition.required ? 'bg-green-500 text-white' : 'bg-blue-500 text-white'
            }`}
            style={{ minHeight: '0.6rem', lineHeight: '0.6rem' }}
          >
            {condition.name}
          </span>
        ))}
      </div>
      <div className="flex flex-wrap mt-2">
        {format.tags && format.tags.map(tag => (
          <span key={tag} className="bg-blue-100 text-blue-800 text-xs font-medium mr-2 mb-1 px-2.5 py-0.5 rounded dark:bg-blue-900 dark:text-blue-300">
            {tag}
          </span>
        ))}
      </div>
    </div>
  );
}

FormatCard.propTypes = {
  format: PropTypes.shape({
    id: PropTypes.number.isRequired,
    name: PropTypes.string.isRequired,
    description: PropTypes.string,
    conditions: PropTypes.arrayOf(PropTypes.shape({
      name: PropTypes.string.isRequired,
      negate: PropTypes.bool,
      required: PropTypes.bool,
    })),
    date_modified: PropTypes.string.isRequired,
    tags: PropTypes.arrayOf(PropTypes.string),
  }).isRequired,
  onEdit: PropTypes.func.isRequired,
  onClone: PropTypes.func.isRequired, // New prop for cloning
  showDate: PropTypes.bool.isRequired,
  formatDate: PropTypes.func.isRequired,
};

export default FormatCard;
