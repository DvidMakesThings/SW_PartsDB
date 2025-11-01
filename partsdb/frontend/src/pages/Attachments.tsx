import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getComponent, listAttachments, uploadAttachment } from '../api';
import { Component, Attachment } from '../api/types';
import { useToast } from '../components/Toast';
import Button from '../components/Button';
import DataTable from '../components/DataTable';
import FileDropzone from '../components/FileDropzone';
import Modal from '../components/Modal';
import Select from '../components/Select';

const Attachments: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [component, setComponent] = useState<Component | null>(null);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [attachmentType, setAttachmentType] = useState<'datasheet' | 'three_d' | 'photo' | 'appnote' | 'other'>('datasheet');
  const { addToast } = useToast();

  // Fetch component and its attachments
  useEffect(() => {
    const loadData = async () => {
      if (!id) return;
      
      setLoading(true);
      setError(null);
      
      try {
        // Load component details
        const componentData = await getComponent(id);
        setComponent(componentData);
        
        // Load attachments
        const attachmentsData = await listAttachments({ component_id: id });
        setAttachments(attachmentsData.results);
      } catch (err: any) {
        setError(`Failed to load data: ${err.message}`);
        addToast(`Error: ${err.message}`, 'error');
      } finally {
        setLoading(false);
      }
    };
    
    loadData();
  }, [id, addToast]);

  // Handle file upload
  const handleFileSelect = async (file: File) => {
    if (!id) return;
    
    try {
      await uploadAttachment(id, file, attachmentType);
      addToast(`${attachmentType} uploaded successfully`, 'success');
      
      // Refresh attachments list
      const refreshedAttachments = await listAttachments({ component_id: id });
      setAttachments(refreshedAttachments.results);
      
      // Close modal
      setIsUploadModalOpen(false);
    } catch (err: any) {
      addToast(`Error uploading file: ${err.message}`, 'error');
    }
  };

  // Table columns
  const columns = [
    { header: 'Type', accessor: ((item: Attachment) => item.type) as (item: Attachment) => React.ReactNode },
    {
      header: 'File',
      accessor: (item: Attachment) => (
        <a
          href={item.file}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-600 hover:text-blue-800 underline"
        >
          View File
        </a>
      ),
    },
    { 
      header: 'Source',
      accessor: ((item: Attachment) => item.source_url ? (
        <a 
          href={item.source_url} 
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-600 hover:text-blue-800 underline"
        >
          Source Link
        </a>
      ) : '-') as (item: Attachment) => React.ReactNode
    },
    { header: 'Added', accessor: ((item: Attachment) => new Date(item.created_at).toLocaleDateString()) as (item: Attachment) => React.ReactNode },
  ];

  if (loading) {
    return <div className="py-4 text-center">Loading attachments...</div>;
  }

  if (error) {
    return <div className="py-4 text-center text-red-600">{error}</div>;
  }

  if (!component) {
    return <div className="py-4 text-center text-red-600">Component not found</div>;
  }

  return (
    <div>
      <div className="mb-6">
        <Link to={`/components/${id}`} className="text-blue-600 hover:text-blue-800">
          ← Back to Component
        </Link>
        <h1 className="text-2xl font-bold text-gray-900 mt-2">
          Attachments for {component.mpn}
          <span className="ml-2 text-lg font-normal text-gray-600">
            {component.manufacturer}
          </span>
        </h1>
      </div>

      <div className="mb-6 flex justify-between items-center">
        <p className="text-gray-700">
          Manage files and datasheets associated with this component.
        </p>
        <Button onClick={() => setIsUploadModalOpen(true)} variant="primary">
          Upload New Attachment
        </Button>
      </div>

      {attachments.length > 0 ? (
        <DataTable
          data={attachments}
          columns={columns}
          keyField="id"
        />
      ) : (
        <div className="bg-white rounded-lg shadow p-6 text-center">
          <p className="text-gray-500 mb-4">No attachments found for this component.</p>
          <Button onClick={() => setIsUploadModalOpen(true)} variant="secondary">
            Upload Your First Attachment
          </Button>
        </div>
      )}

      {/* Upload Modal */}
      <Modal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        title="Upload Attachment"
      >
        <div className="space-y-4">
          <Select
            id="attachment-type"
            label="Attachment Type"
            value={attachmentType}
            onChange={(e) => setAttachmentType(e.target.value as any)}
            options={[
              { value: 'datasheet', label: 'Datasheet' },
              { value: 'three_d', label: '3D Model' },
              { value: 'photo', label: 'Photo' },
              { value: 'appnote', label: 'Application Note' },
              { value: 'other', label: 'Other' },
            ]}
            required
          />
          <FileDropzone
            onFileSelect={handleFileSelect}
            accept={
              attachmentType === 'datasheet'
                ? '.pdf'
                : attachmentType === 'three_d'
                ? '.step,.stp'
                : attachmentType === 'photo'
                ? '.jpg,.jpeg,.png'
                : undefined
            }
          />
          <div className="flex justify-end space-x-2 mt-4">
            <Button variant="secondary" onClick={() => setIsUploadModalOpen(false)}>
              Cancel
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default Attachments;